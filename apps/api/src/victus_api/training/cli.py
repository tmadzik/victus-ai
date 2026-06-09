"""Training CLI — produces the Pathway A EDL checkpoint + meta sidecar.

Two pipelines behind the same CLI:

* Default (``sequential_v1``) — vanilla EDL, the original training path.
* ``--enable-dann`` (``dann_v1``) — shared feature extractor + EDL task head +
  gradient-reversal domain head trained against
  ``{CLINICAL_GRADE, CHW_TAPE_MEASURE, SYNTHETIC}``. The CHW domain is
  synthesised by noise-injecting each CLINICAL_GRADE row
  ``--chw-noise-multiplier`` times.

Example:

    uv sync --extra ml
    uv run python -m victus_api.training.cli \\
        --data-dir "/path/to/datasets" \\
        --output apps/api/models/triage_edl_v1.pt \\
        --epochs 80 --enable-dann --chw-noise-multiplier 4 --grl-gamma 10

Activate the checkpoint at runtime:

    export VICTUS_TRIAGE_MODEL_PATH=apps/api/models/triage_edl_v1.pt
    pnpm api:dev

The runtime ``EvidentialTorchModel`` validates the meta sidecar against the
current ``FEATURE_NAMES`` and ``RISK_CLASSES`` at startup; an incompatible
checkpoint refuses to load rather than silently mis-serving.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch

from victus_api.config import get_settings
from victus_api.core.logging import configure_logging, get_logger
from victus_api.training.datasets import (
    class_distribution,
    domain_distribution,
    load_all,
    source_distribution,
    synthesize_chw_domain,
)
from victus_api.training.export import save_checkpoint
from victus_api.training.harmonize import (
    CLASS_INDEX,
    DOMAIN_INDEX,
    DOMAINS,
    HarmonizedRecord,
)
from victus_api.training.loop import (
    train_dann_evidential_model,
    train_evidential_model,
)
from victus_api.training.scaling import StandardScaler
from victus_api.triage.edl.dirichlet import (
    build_dann_evidential_model,
    build_evidential_mlp,
)
from victus_api.triage.features import FEATURE_NAMES
from victus_api.triage.schemas import RISK_CLASSES

DEFAULT_HIDDEN_DIMS: tuple[int, ...] = (64, 32)
DEFAULT_DATA_DIR = Path(
    "/Users/taxbookair/Documents/Work/Joolr/V/Victus/Victus x VFD/Victus/datasets"
)


def _build_matrix(
    records: list[HarmonizedRecord],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    x = np.asarray([r.feature_vector() for r in records], dtype=np.float32)
    y = np.asarray([CLASS_INDEX[r.risk_class] for r in records], dtype=np.int64)
    d = np.asarray([DOMAIN_INDEX[r.domain] for r in records], dtype=np.int64)
    return x, y, d


def _stratified_split(
    x: np.ndarray,
    y: np.ndarray,
    d: np.ndarray,
    *,
    val_frac: float,
    seed: int,
) -> tuple[
    np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray
]:
    """Stratify on the joint (class, domain) cell so the val set covers every
    cell uniformly. Falls back to class-only stratification for cells that
    are too small (<2 samples) to split.
    """
    rng = np.random.default_rng(seed)
    train_idx: list[int] = []
    val_idx: list[int] = []
    n_classes = int(y.max()) + 1
    n_domains = int(d.max()) + 1
    for cls in range(n_classes):
        for dom in range(n_domains):
            idxs = np.where((y == cls) & (d == dom))[0]
            if len(idxs) == 0:
                continue
            rng.shuffle(idxs)
            n_val = max(1, round(len(idxs) * val_frac)) if len(idxs) >= 2 else 0
            val_idx.extend(idxs[:n_val].tolist())
            train_idx.extend(idxs[n_val:].tolist())
    train_idx_arr = np.asarray(train_idx, dtype=np.int64)
    val_idx_arr = np.asarray(val_idx, dtype=np.int64)
    rng.shuffle(train_idx_arr)
    rng.shuffle(val_idx_arr)
    return (
        x[train_idx_arr],
        y[train_idx_arr],
        d[train_idx_arr],
        x[val_idx_arr],
        y[val_idx_arr],
        d[val_idx_arr],
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Train the Pathway A EDL classifier.")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help="Root containing body_fat_prediction/, diabetes/, heart_disease_ml/, "
        "healthcare-dataset-stroke-data.csv",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("apps/api/models/triage_edl_v1.pt"),
        help="Checkpoint output path (a sibling .meta.json is written next to it).",
    )
    parser.add_argument("--epochs", type=int, default=60)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--lr", type=float, default=5e-4)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--annealing-epochs", type=int, default=10)
    parser.add_argument("--val-frac", type=float, default=0.15)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--version", default="1.0.0")
    parser.add_argument(
        "--hidden", type=int, nargs="+", default=list(DEFAULT_HIDDEN_DIMS)
    )

    # DANN-specific knobs
    parser.add_argument(
        "--enable-dann",
        action="store_true",
        help="Train the DANN-augmented architecture (dann_v1).",
    )
    parser.add_argument(
        "--chw-noise-multiplier",
        type=int,
        default=4,
        help="Number of noise-injected CHW replicates per CLINICAL_GRADE record.",
    )
    parser.add_argument(
        "--grl-gamma",
        type=float,
        default=10.0,
        help="Ganin curriculum slope: λ(p) = 2/(1+e^{-γp}) − 1.",
    )
    parser.add_argument(
        "--domain-hidden",
        type=int,
        default=32,
        help="Hidden width of the domain-classifier head.",
    )
    parser.add_argument(
        "--class-balanced",
        action="store_true",
        default=True,
        help="Apply sklearn 'balanced' class weights to the EDL fit term "
        "(default ON; pass --no-class-balanced to disable).",
    )
    parser.add_argument(
        "--no-class-balanced",
        dest="class_balanced",
        action="store_false",
    )
    parser.add_argument(
        "--focal-gamma",
        type=float,
        default=0.0,
        help="Focal-style hard-example weighting on the EDL fit term: "
        "scale = (1 − E[p_y])^γ. 0 disables; 1.5–2.0 strongly down-weights easy examples.",
    )

    args = parser.parse_args(argv)

    configure_logging(get_settings())
    log = get_logger("victus_api.training.cli")

    log.info("loading_datasets", data_dir=str(args.data_dir))
    records = load_all(args.data_dir)
    if not records:
        log.error("no_records_loaded", data_dir=str(args.data_dir))
        return 2

    if args.enable_dann:
        chw_records = synthesize_chw_domain(
            records, k_multiplier=args.chw_noise_multiplier, seed=args.seed
        )
        records = records + chw_records

    log.info(
        "dataset_distribution",
        total=len(records),
        sources=source_distribution(records),
        classes={c.value: n for c, n in class_distribution(records).items()},
        domains={d.value: n for d, n in domain_distribution(records).items()},
    )

    x, y, d = _build_matrix(records)
    x_train, y_train, d_train, x_val, y_val, d_val = _stratified_split(
        x, y, d, val_frac=args.val_frac, seed=args.seed
    )
    log.info("split_sizes", train=len(x_train), val=len(x_val))

    scaler = StandardScaler.fit(x_train)
    x_train_s = scaler.transform(x_train)
    x_val_s = scaler.transform(x_val)

    hidden_dims = tuple(int(h) for h in args.hidden)
    domain_labels = tuple(dm.value for dm in DOMAINS)
    output_path = args.output.resolve()
    torch.manual_seed(args.seed)

    if args.enable_dann:
        model = build_dann_evidential_model(
            input_dim=len(FEATURE_NAMES),
            num_classes=len(RISK_CLASSES),
            num_domains=len(DOMAINS),
            hidden_dims=hidden_dims,
            domain_hidden=args.domain_hidden,
            dropout=0.15,
        )
        final_metrics, history = train_dann_evidential_model(
            model=model,
            x_train=x_train_s,
            y_train=y_train,
            d_train=d_train,
            x_val=x_val_s,
            y_val=y_val,
            d_val=d_val,
            num_classes=len(RISK_CLASSES),
            num_domains=len(DOMAINS),
            domain_labels=domain_labels,
            epochs=args.epochs,
            batch_size=args.batch_size,
            lr=args.lr,
            weight_decay=args.weight_decay,
            annealing_epochs=args.annealing_epochs,
            grl_gamma=args.grl_gamma,
            class_balanced=args.class_balanced,
            focal_gamma=args.focal_gamma,
            seed=args.seed,
        )
        training_payload = {
            "final": final_metrics.to_dict(),
            "history": history,
            "epochs": args.epochs,
            "batch_size": args.batch_size,
            "lr": args.lr,
            "weight_decay": args.weight_decay,
            "annealing_epochs": args.annealing_epochs,
            "val_frac": args.val_frac,
            "seed": args.seed,
            "grl_gamma": args.grl_gamma,
            "chw_noise_multiplier": args.chw_noise_multiplier,
            "domain_hidden": args.domain_hidden,
            "class_balanced": args.class_balanced,
            "focal_gamma": args.focal_gamma,
        }
        save_checkpoint(
            model=model,
            checkpoint_path=output_path,
            feature_names=FEATURE_NAMES,
            label_mapping=tuple(c.value for c in RISK_CLASSES),
            hidden_dims=hidden_dims,
            scaler=scaler,
            version=args.version,
            training_metrics=training_payload,
            source_distribution=source_distribution(records),
            class_distribution={
                c.value: n for c, n in class_distribution(records).items()
            },
            architecture="dann_v1",
            domain_mapping=domain_labels,
            domain_hidden=args.domain_hidden,
            domain_distribution={
                dm.value: n for dm, n in domain_distribution(records).items()
            },
        )
        summary_metrics = final_metrics.to_dict()
    else:
        model = build_evidential_mlp(
            input_dim=len(FEATURE_NAMES),
            num_classes=len(RISK_CLASSES),
            hidden_dims=hidden_dims,
            dropout=0.15,
        )
        final_metrics, history = train_evidential_model(
            model=model,
            x_train=x_train_s,
            y_train=y_train,
            x_val=x_val_s,
            y_val=y_val,
            num_classes=len(RISK_CLASSES),
            epochs=args.epochs,
            batch_size=args.batch_size,
            lr=args.lr,
            weight_decay=args.weight_decay,
            annealing_epochs=args.annealing_epochs,
            seed=args.seed,
        )
        save_checkpoint(
            model=model,
            checkpoint_path=output_path,
            feature_names=FEATURE_NAMES,
            label_mapping=tuple(c.value for c in RISK_CLASSES),
            hidden_dims=hidden_dims,
            scaler=scaler,
            version=args.version,
            training_metrics={
                "final": final_metrics.to_dict(),
                "history": history,
                "epochs": args.epochs,
                "batch_size": args.batch_size,
                "lr": args.lr,
                "weight_decay": args.weight_decay,
                "annealing_epochs": args.annealing_epochs,
                "val_frac": args.val_frac,
                "seed": args.seed,
            },
            source_distribution=source_distribution(records),
            class_distribution={
                c.value: n for c, n in class_distribution(records).items()
            },
            architecture="sequential_v1",
        )
        summary_metrics = final_metrics.to_dict()

    summary = {
        "checkpoint": str(output_path),
        "meta": str(output_path.with_suffix(output_path.suffix + ".meta.json")),
        "architecture": "dann_v1" if args.enable_dann else "sequential_v1",
        "metrics": summary_metrics,
        "n_train": len(x_train),
        "n_val": len(x_val),
    }
    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
