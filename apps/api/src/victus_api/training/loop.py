"""Training loop + calibration metrics.

Two training variants live here:

* :func:`train_evidential_model` — vanilla EDL (no domain head).
* :func:`train_dann_evidential_model` — EDL task head + GRL → domain head.
  The combined loss is ``L_EDL(task) + λ(p) · CE(domain)`` with Ganin's
  curriculum ``λ(p) = 2/(1+e^{-γp}) − 1`` so the adversary ramps up smoothly
  from 0. Domain-balanced batches are constructed via
  :class:`torch.utils.data.WeightedRandomSampler` because raw frequency would
  otherwise let the adversary trivially predict SYNTHETIC.

Calibration assessment is non-negotiable for an evidential classifier: a model
that produces overconfident predictions on cases it should be uncertain about
defeats the purpose of EDL. We compute the standard 15-bin Expected Calibration
Error and the multi-class Brier score plus mean vacuity stratified by
correctness. The DANN variant additionally reports domain-head accuracy on val
(lower = better; chance = 1/num_domains indicates successful invariance) and
per-domain task accuracy (gap measures residual domain bias).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import torch
from torch import Tensor, nn
from torch.utils.data import DataLoader, TensorDataset, WeightedRandomSampler

from victus_api.core.logging import get_logger
from victus_api.triage.edl.dirichlet import edl_mse_loss

log = get_logger(__name__)


@dataclass(slots=True)
class CalibrationMetrics:
    accuracy: float
    macro_f1: float
    expected_calibration_error: float
    brier_score: float
    mean_vacuity_correct: float
    mean_vacuity_incorrect: float
    val_loss: float

    def to_dict(self) -> dict[str, float]:
        return {
            "accuracy": self.accuracy,
            "macro_f1": self.macro_f1,
            "expected_calibration_error": self.expected_calibration_error,
            "brier_score": self.brier_score,
            "mean_vacuity_correct": self.mean_vacuity_correct,
            "mean_vacuity_incorrect": self.mean_vacuity_incorrect,
            "val_loss": self.val_loss,
        }


def _to_dataset(x: np.ndarray, y: np.ndarray, num_classes: int) -> TensorDataset:
    x_t = torch.from_numpy(x.astype(np.float32))
    y_t = torch.from_numpy(y.astype(np.int64))
    y_oh = torch.nn.functional.one_hot(y_t, num_classes=num_classes).float()
    return TensorDataset(x_t, y_t, y_oh)


def train_evidential_model(
    *,
    model: nn.Module,
    x_train: np.ndarray,
    y_train: np.ndarray,
    x_val: np.ndarray,
    y_val: np.ndarray,
    num_classes: int,
    epochs: int = 60,
    batch_size: int = 128,
    lr: float = 5e-4,
    weight_decay: float = 1e-4,
    annealing_epochs: int = 10,
    device: torch.device | None = None,
    seed: int = 17,
) -> tuple[CalibrationMetrics, list[dict[str, float]]]:
    device = device or torch.device("cpu")
    torch.manual_seed(seed)
    np.random.seed(seed)

    model = model.to(device)
    optim = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)

    train_set = _to_dataset(x_train, y_train, num_classes)
    val_set = _to_dataset(x_val, y_val, num_classes)
    train_loader = DataLoader(
        train_set, batch_size=batch_size, shuffle=True, drop_last=False
    )
    val_loader = DataLoader(val_set, batch_size=512, shuffle=False, drop_last=False)

    history: list[dict[str, float]] = []
    for epoch in range(1, epochs + 1):
        model.train()
        running = 0.0
        n_seen = 0
        for xb, _, yb_oh in train_loader:
            xb = xb.to(device)
            yb_oh = yb_oh.to(device)
            optim.zero_grad(set_to_none=True)
            evidence = model(xb)
            loss = edl_mse_loss(
                evidence, yb_oh, epoch=epoch, annealing_epochs=annealing_epochs
            )
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=5.0)
            optim.step()
            running += float(loss.detach()) * xb.shape[0]
            n_seen += xb.shape[0]
        train_loss = running / max(n_seen, 1)

        metrics = _evaluate(
            model, val_loader, device=device, epoch=epoch, annealing_epochs=annealing_epochs
        )
        history.append(
            {
                "epoch": epoch,
                "train_loss": train_loss,
                "val_loss": metrics.val_loss,
                "val_accuracy": metrics.accuracy,
                "val_ece": metrics.expected_calibration_error,
                "val_brier": metrics.brier_score,
                "mean_u_correct": metrics.mean_vacuity_correct,
                "mean_u_incorrect": metrics.mean_vacuity_incorrect,
            }
        )
        if epoch == 1 or epoch % 5 == 0 or epoch == epochs:
            log.info(
                "epoch",
                epoch=epoch,
                train_loss=round(train_loss, 4),
                val_loss=round(metrics.val_loss, 4),
                val_acc=round(metrics.accuracy, 4),
                ece=round(metrics.expected_calibration_error, 4),
            )
    final = _evaluate(
        model, val_loader, device=device, epoch=epochs, annealing_epochs=annealing_epochs
    )
    return final, history


def _evaluate(
    model: nn.Module,
    loader: DataLoader[tuple[Tensor, Tensor, Tensor]],
    *,
    device: torch.device,
    epoch: int,
    annealing_epochs: int,
) -> CalibrationMetrics:
    model.eval()
    confs: list[np.ndarray] = []
    preds: list[np.ndarray] = []
    targets: list[np.ndarray] = []
    vacuities: list[np.ndarray] = []
    val_loss_total = 0.0
    n_seen = 0
    num_classes = 0
    with torch.no_grad():
        for xb, yb, yb_oh in loader:
            xb = xb.to(device)
            yb_oh = yb_oh.to(device)
            evidence = model(xb)
            loss = edl_mse_loss(
                evidence, yb_oh, epoch=epoch, annealing_epochs=annealing_epochs
            )
            val_loss_total += float(loss) * xb.shape[0]
            n_seen += xb.shape[0]
            alpha = evidence + 1.0
            strength = alpha.sum(dim=-1, keepdim=True)
            probs = (alpha / strength).cpu().numpy()
            num_classes = probs.shape[-1]
            vac = (num_classes / strength.squeeze(-1)).cpu().numpy()
            confs.append(probs)
            preds.append(probs.argmax(axis=-1))
            targets.append(yb.numpy())
            vacuities.append(vac)

    probs_arr = np.concatenate(confs, axis=0)
    preds_arr = np.concatenate(preds, axis=0)
    targets_arr = np.concatenate(targets, axis=0)
    vac_arr = np.concatenate(vacuities, axis=0)
    accuracy = float((preds_arr == targets_arr).mean())
    macro_f1 = _macro_f1(preds_arr, targets_arr, num_classes=num_classes)
    ece = _expected_calibration_error(probs_arr, targets_arr, n_bins=15)
    brier = _brier_multiclass(probs_arr, targets_arr, num_classes=num_classes)
    correct_mask = preds_arr == targets_arr
    mean_u_correct = float(vac_arr[correct_mask].mean()) if correct_mask.any() else 0.0
    mean_u_incorrect = (
        float(vac_arr[~correct_mask].mean()) if (~correct_mask).any() else 0.0
    )

    return CalibrationMetrics(
        accuracy=accuracy,
        macro_f1=macro_f1,
        expected_calibration_error=ece,
        brier_score=brier,
        mean_vacuity_correct=mean_u_correct,
        mean_vacuity_incorrect=mean_u_incorrect,
        val_loss=val_loss_total / max(n_seen, 1),
    )


def _expected_calibration_error(
    probs: np.ndarray, targets: np.ndarray, *, n_bins: int = 15
) -> float:
    confidences = probs.max(axis=-1)
    preds = probs.argmax(axis=-1)
    correct = (preds == targets).astype(np.float64)
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    n = len(confidences)
    for i in range(n_bins):
        lo, hi = bins[i], bins[i + 1]
        mask = (
            (confidences > lo) & (confidences <= hi)
            if i > 0
            else (confidences >= lo) & (confidences <= hi)
        )
        weight = mask.sum() / max(n, 1)
        if weight == 0.0:
            continue
        bin_acc = correct[mask].mean()
        bin_conf = confidences[mask].mean()
        ece += weight * abs(bin_acc - bin_conf)
    return float(ece)


def _brier_multiclass(probs: np.ndarray, targets: np.ndarray, *, num_classes: int) -> float:
    one_hot = np.zeros((len(targets), num_classes), dtype=np.float64)
    one_hot[np.arange(len(targets)), targets] = 1.0
    return float(np.mean(np.sum((probs - one_hot) ** 2, axis=-1)))


def _macro_f1(preds: np.ndarray, targets: np.ndarray, *, num_classes: int) -> float:
    f1s: list[float] = []
    for c in range(num_classes):
        tp = float(((preds == c) & (targets == c)).sum())
        fp = float(((preds == c) & (targets != c)).sum())
        fn = float(((preds != c) & (targets == c)).sum())
        denom = 2 * tp + fp + fn
        f1s.append(2 * tp / denom if denom > 0.0 else 0.0)
    return float(np.mean(f1s))


# ---------------------------------------------------------------------------
# DANN training
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class DannMetrics:
    task: CalibrationMetrics
    domain_accuracy: float
    domain_chance: float
    per_domain_task_accuracy: dict[str, float]
    grl_lambda_final: float

    def to_dict(self) -> dict[str, object]:
        return {
            "task": self.task.to_dict(),
            "domain_accuracy": self.domain_accuracy,
            "domain_chance": self.domain_chance,
            "per_domain_task_accuracy": self.per_domain_task_accuracy,
            "grl_lambda_final": self.grl_lambda_final,
        }


def _grl_lambda(p: float, gamma: float) -> float:
    """Ganin & Lempitsky curriculum: λ(p) = 2 / (1 + e^{-γp}) − 1, p ∈ [0, 1]."""
    p = max(0.0, min(1.0, p))
    return 2.0 / (1.0 + math.exp(-gamma * p)) - 1.0


def _domain_balanced_sampler(
    domain_ids: np.ndarray, *, seed: int
) -> WeightedRandomSampler:
    counts = np.bincount(domain_ids)
    counts = np.where(counts == 0, 1, counts)
    weights = 1.0 / counts[domain_ids]
    generator = torch.Generator().manual_seed(seed)
    return WeightedRandomSampler(
        weights=torch.tensor(weights, dtype=torch.float64),
        num_samples=len(domain_ids),
        replacement=True,
        generator=generator,
    )


def _joint_class_domain_sampler(
    class_ids: np.ndarray,
    domain_ids: np.ndarray,
    *,
    seed: int,
) -> WeightedRandomSampler:
    """Equalize the expected frequency of every ``(class, domain)`` cell.

    For each sample ``i`` we assign weight ``1 / count(class=y_i, domain=d_i)``
    so cells with fewer samples are over-sampled by exactly the inverse-
    frequency factor. With K=4 classes and D=3 domains, the expected number of
    samples per cell per epoch becomes ``len(class_ids) / 12``.

    Cells with zero training samples are clamped to weight 0 (they cannot be
    sampled — they simply don't exist).
    """
    if class_ids.shape != domain_ids.shape:
        raise ValueError("class_ids and domain_ids must have the same shape")
    # Build a dense (K, D) count matrix.
    n_classes = int(class_ids.max()) + 1
    n_domains = int(domain_ids.max()) + 1
    cell_counts = np.zeros((n_classes, n_domains), dtype=np.int64)
    for c, d in zip(class_ids, domain_ids, strict=True):
        cell_counts[int(c), int(d)] += 1
    # Per-sample weight from its cell count.
    sample_cell_counts = cell_counts[class_ids, domain_ids]
    safe_counts = np.where(sample_cell_counts == 0, 1, sample_cell_counts)
    weights = 1.0 / safe_counts.astype(np.float64)
    weights[sample_cell_counts == 0] = 0.0
    generator = torch.Generator().manual_seed(seed)
    return WeightedRandomSampler(
        weights=torch.tensor(weights, dtype=torch.float64),
        num_samples=len(class_ids),
        replacement=True,
        generator=generator,
    )


def compute_balanced_class_weights(
    class_ids: np.ndarray, *, num_classes: int
) -> np.ndarray:
    """sklearn 'balanced' class weights: ``w_c = N / (K · n_c)``.

    For zero-count classes (none in the training split) we set the weight to
    1.0 — they will not contribute to the loss because no sample has them as
    the target.
    """
    counts = np.bincount(class_ids, minlength=num_classes).astype(np.float64)
    n = float(class_ids.shape[0])
    weights = np.where(counts > 0, n / (num_classes * counts), 1.0)
    return weights.astype(np.float32)


def train_dann_evidential_model(
    *,
    model: nn.Module,
    x_train: np.ndarray,
    y_train: np.ndarray,
    d_train: np.ndarray,
    x_val: np.ndarray,
    y_val: np.ndarray,
    d_val: np.ndarray,
    num_classes: int,
    num_domains: int,
    domain_labels: tuple[str, ...],
    epochs: int = 80,
    batch_size: int = 128,
    lr: float = 1e-3,
    weight_decay: float = 1e-4,
    annealing_epochs: int = 160,
    grl_gamma: float = 10.0,
    class_balanced: bool = True,
    focal_gamma: float = 0.0,
    device: torch.device | None = None,
    seed: int = 17,
) -> tuple[DannMetrics, list[dict[str, float]]]:
    device = device or torch.device("cpu")
    torch.manual_seed(seed)
    np.random.seed(seed)

    model = model.to(device)
    optim = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)

    x_t = torch.from_numpy(x_train.astype(np.float32))
    y_t = torch.from_numpy(y_train.astype(np.int64))
    d_t = torch.from_numpy(d_train.astype(np.int64))
    y_oh = torch.nn.functional.one_hot(y_t, num_classes=num_classes).float()
    train_set: TensorDataset = TensorDataset(x_t, y_t, y_oh, d_t)
    sampler = _joint_class_domain_sampler(y_train, d_train, seed=seed)
    train_loader: DataLoader[tuple[Tensor, Tensor, Tensor, Tensor]] = DataLoader(
        train_set, batch_size=batch_size, sampler=sampler, drop_last=False
    )

    # Class weights for the loss — sklearn 'balanced' convention.
    class_weights_np = (
        compute_balanced_class_weights(y_train, num_classes=num_classes)
        if class_balanced
        else None
    )
    class_weights_t = (
        torch.from_numpy(class_weights_np).to(device)
        if class_weights_np is not None
        else None
    )

    x_v = torch.from_numpy(x_val.astype(np.float32))
    y_v = torch.from_numpy(y_val.astype(np.int64))
    d_v = torch.from_numpy(d_val.astype(np.int64))
    y_v_oh = torch.nn.functional.one_hot(y_v, num_classes=num_classes).float()
    val_set: TensorDataset = TensorDataset(x_v, y_v, y_v_oh, d_v)
    val_loader: DataLoader[tuple[Tensor, Tensor, Tensor, Tensor]] = DataLoader(
        val_set, batch_size=512, shuffle=False, drop_last=False
    )

    ce = nn.CrossEntropyLoss()
    grl_lambda_final = 0.0
    history: list[dict[str, float]] = []
    for epoch in range(1, epochs + 1):
        model.train()
        running_task = 0.0
        running_dom = 0.0
        n_seen = 0
        progress = epoch / max(1, epochs)
        grl_lambda = _grl_lambda(progress, grl_gamma)
        for xb, _, yb_oh, db in train_loader:
            xb = xb.to(device)
            yb_oh = yb_oh.to(device)
            db = db.to(device)
            optim.zero_grad(set_to_none=True)
            evidence, domain_logits = model(xb, grl_alpha=grl_lambda)
            task_loss = edl_mse_loss(
                evidence,
                yb_oh,
                epoch=epoch,
                annealing_epochs=annealing_epochs,
                class_weights=class_weights_t,
                focal_gamma=focal_gamma,
            )
            dom_loss = ce(domain_logits, db)
            loss = task_loss + dom_loss
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=5.0)
            optim.step()
            running_task += float(task_loss.detach()) * xb.shape[0]
            running_dom += float(dom_loss.detach()) * xb.shape[0]
            n_seen += xb.shape[0]
        train_task_loss = running_task / max(n_seen, 1)
        train_dom_loss = running_dom / max(n_seen, 1)
        grl_lambda_final = grl_lambda

        metrics = _evaluate_dann(
            model,
            val_loader,
            device=device,
            epoch=epoch,
            annealing_epochs=annealing_epochs,
            grl_lambda=grl_lambda,
            num_domains=num_domains,
            domain_labels=domain_labels,
        )
        history.append(
            {
                "epoch": epoch,
                "grl_lambda": grl_lambda,
                "train_task_loss": train_task_loss,
                "train_domain_loss": train_dom_loss,
                "val_task_loss": metrics.task.val_loss,
                "val_accuracy": metrics.task.accuracy,
                "val_ece": metrics.task.expected_calibration_error,
                "val_brier": metrics.task.brier_score,
                "val_domain_accuracy": metrics.domain_accuracy,
                "mean_u_correct": metrics.task.mean_vacuity_correct,
                "mean_u_incorrect": metrics.task.mean_vacuity_incorrect,
            }
        )
        if epoch == 1 or epoch % 5 == 0 or epoch == epochs:
            log.info(
                "dann_epoch",
                epoch=epoch,
                grl_lambda=round(grl_lambda, 3),
                task_loss=round(train_task_loss, 4),
                domain_loss=round(train_dom_loss, 4),
                val_acc=round(metrics.task.accuracy, 4),
                val_ece=round(metrics.task.expected_calibration_error, 4),
                domain_acc=round(metrics.domain_accuracy, 4),
                per_domain_acc={
                    k: round(v, 3) for k, v in metrics.per_domain_task_accuracy.items()
                },
            )

    final = _evaluate_dann(
        model,
        val_loader,
        device=device,
        epoch=epochs,
        annealing_epochs=annealing_epochs,
        grl_lambda=grl_lambda_final,
        num_domains=num_domains,
        domain_labels=domain_labels,
    )
    return final, history


def _evaluate_dann(
    model: nn.Module,
    loader: DataLoader[tuple[Tensor, Tensor, Tensor, Tensor]],
    *,
    device: torch.device,
    epoch: int,
    annealing_epochs: int,
    grl_lambda: float,
    num_domains: int,
    domain_labels: tuple[str, ...],
) -> DannMetrics:
    model.eval()
    confs: list[np.ndarray] = []
    preds: list[np.ndarray] = []
    targets: list[np.ndarray] = []
    domains: list[np.ndarray] = []
    domain_preds: list[np.ndarray] = []
    vacuities: list[np.ndarray] = []
    val_loss_total = 0.0
    n_seen = 0
    num_classes = 0
    with torch.no_grad():
        for xb, yb, yb_oh, db in loader:
            xb = xb.to(device)
            yb_oh = yb_oh.to(device)
            db = db.to(device)
            evidence, domain_logits = model(xb, grl_alpha=grl_lambda)
            loss = edl_mse_loss(
                evidence, yb_oh, epoch=epoch, annealing_epochs=annealing_epochs
            )
            val_loss_total += float(loss) * xb.shape[0]
            n_seen += xb.shape[0]
            alpha = evidence + 1.0
            strength = alpha.sum(dim=-1, keepdim=True)
            probs = (alpha / strength).cpu().numpy()
            num_classes = probs.shape[-1]
            vac = (num_classes / strength.squeeze(-1)).cpu().numpy()
            confs.append(probs)
            preds.append(probs.argmax(axis=-1))
            targets.append(yb.numpy())
            vacuities.append(vac)
            domains.append(db.cpu().numpy())
            domain_preds.append(domain_logits.argmax(dim=-1).cpu().numpy())

    probs_arr = np.concatenate(confs, axis=0)
    preds_arr = np.concatenate(preds, axis=0)
    targets_arr = np.concatenate(targets, axis=0)
    vac_arr = np.concatenate(vacuities, axis=0)
    domains_arr = np.concatenate(domains, axis=0)
    domain_preds_arr = np.concatenate(domain_preds, axis=0)

    accuracy = float((preds_arr == targets_arr).mean())
    macro_f1 = _macro_f1(preds_arr, targets_arr, num_classes=num_classes)
    ece = _expected_calibration_error(probs_arr, targets_arr, n_bins=15)
    brier = _brier_multiclass(probs_arr, targets_arr, num_classes=num_classes)
    correct_mask = preds_arr == targets_arr
    mean_u_correct = float(vac_arr[correct_mask].mean()) if correct_mask.any() else 0.0
    mean_u_incorrect = (
        float(vac_arr[~correct_mask].mean()) if (~correct_mask).any() else 0.0
    )

    task = CalibrationMetrics(
        accuracy=accuracy,
        macro_f1=macro_f1,
        expected_calibration_error=ece,
        brier_score=brier,
        mean_vacuity_correct=mean_u_correct,
        mean_vacuity_incorrect=mean_u_incorrect,
        val_loss=val_loss_total / max(n_seen, 1),
    )

    domain_accuracy = float((domain_preds_arr == domains_arr).mean())
    per_domain: dict[str, float] = {}
    for d_idx in range(num_domains):
        mask = domains_arr == d_idx
        label = domain_labels[d_idx] if d_idx < len(domain_labels) else f"d{d_idx}"
        if mask.any():
            per_domain[label] = float((preds_arr[mask] == targets_arr[mask]).mean())
        else:
            per_domain[label] = float("nan")

    return DannMetrics(
        task=task,
        domain_accuracy=domain_accuracy,
        domain_chance=1.0 / num_domains,
        per_domain_task_accuracy=per_domain,
        grl_lambda_final=grl_lambda,
    )
