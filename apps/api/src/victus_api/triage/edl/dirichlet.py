"""Evidential Deep Learning — Dirichlet head, Sensoy loss, uncertainty math.

Reference: Sensoy, Kaplan, Kandemir, *Evidential Deep Learning to Quantify
Classification Uncertainty*, NeurIPS 2018.

Conventions
-----------
``e``        non-negative evidence, ``e = softplus(logits)``
``alpha``    Dirichlet parameters, ``alpha = e + 1`` (uniform prior)
``S``        Dirichlet strength, ``S = sum(alpha) = sum(e) + K``
``p``        expected categorical probability, ``E[p_k] = alpha_k / S``
``u``        Dirichlet vacuity, ``u = K / S`` (∈ [0, 1])

Uncertainty decomposition
-------------------------
* Aleatoric (data uncertainty): the expected categorical entropy
  ``E_{p~Dir(alpha)}[H(p)]`` admits a closed form
  ``digamma(S+1) - sum_k (alpha_k/S) * digamma(alpha_k + 1)``.
* Total predictive entropy: ``H[E[p]] = -sum_k (alpha_k/S) * log(alpha_k/S)``.
* Epistemic (mutual information / BALD): ``H[E[p]] - E[H[p]]``.

This module is the single source of truth for the EDL math used by both the
trained PyTorch backend and the rule-based fallback predictor.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only
    import torch
    from torch import Tensor, nn

EPS = 1e-10


# ---------------------------------------------------------------------------
# Pure-Python uncertainty helpers — no torch dependency.
# These are what the runtime API uses; the model produces evidence as a list
# of floats and the helpers turn it into Dirichlet stats.
# ---------------------------------------------------------------------------


def dirichlet_stats(evidence: list[float]) -> tuple[list[float], float, list[float], float]:
    """Return ``(alpha, strength, expected_probs, vacuity)`` from raw evidence."""
    k = len(evidence)
    if k == 0:
        raise ValueError("Evidence vector must be non-empty.")
    alpha = [max(e, 0.0) + 1.0 for e in evidence]
    strength = sum(alpha)
    expected = [a / strength for a in alpha]
    vacuity = k / strength
    return alpha, strength, expected, vacuity


def _digamma(x: float) -> float:
    """Series-accelerated digamma; accurate to ~1e-12 for x > 0."""
    if x <= 0.0:
        raise ValueError("digamma is undefined for non-positive inputs.")
    result = 0.0
    # Use recursion identity until x is large enough for asymptotic series.
    while x < 6.0:
        result -= 1.0 / x
        x += 1.0
    inv = 1.0 / x
    inv2 = inv * inv
    # Asymptotic expansion: ψ(x) ~ ln(x) - 1/(2x) - 1/(12x^2) + 1/(120x^4) - ...
    result += (
        math.log(x)
        - 0.5 * inv
        - inv2 * (1.0 / 12.0 - inv2 * (1.0 / 120.0 - inv2 / 252.0))
    )
    return result


def expected_dirichlet_entropy(alpha: list[float], strength: float) -> float:
    """Closed-form ``E_{p~Dir(alpha)}[H(p)]`` (aleatoric uncertainty)."""
    digamma_s_plus_1 = _digamma(strength + 1.0)
    aleatoric = digamma_s_plus_1
    for a in alpha:
        aleatoric -= (a / strength) * _digamma(a + 1.0)
    return max(aleatoric, 0.0)


def expected_predictive_entropy(expected_probs: list[float]) -> float:
    """Entropy of the expected categorical distribution ``H[E[p]]``."""
    h = 0.0
    for p in expected_probs:
        if p > EPS:
            h -= p * math.log(p)
    return h


def epistemic_uncertainty(
    alpha: list[float], strength: float, *, aleatoric: float | None = None
) -> float:
    """Mutual information / BALD: ``H[E[p]] - E[H[p]]``.

    ``aleatoric`` may be supplied if already computed to avoid the redundant
    digamma loop; otherwise it is computed in-line.
    """
    expected = [a / strength for a in alpha]
    total = expected_predictive_entropy(expected)
    h_aleatoric = (
        aleatoric if aleatoric is not None else expected_dirichlet_entropy(alpha, strength)
    )
    return max(total - h_aleatoric, 0.0)


# ---------------------------------------------------------------------------
# Torch components — only used by the training pipeline + trained backend.
# Imports are deferred so the API runtime does not require torch unless a
# checkpoint is actually loaded.
# ---------------------------------------------------------------------------


def build_evidential_mlp(
    input_dim: int,
    num_classes: int,
    hidden_dims: tuple[int, ...] = (64, 32),
    dropout: float = 0.1,
) -> nn.Module:
    """Construct a small MLP whose final activation produces non-negative
    evidence via softplus. Designed for tabular Pathway A inputs.

    Architecture identifier: ``sequential_v1`` — the flat ``nn.Sequential`` used
    by the original (non-DANN) training pipeline.
    """
    import torch  # noqa: F401  (kept for diagnostic symmetry)
    from torch import nn

    # NOTE: always emit Dropout (even with p=0) so the Sequential layer indices
    # are invariant between training (dropout > 0) and inference (dropout = 0).
    # Without this, state_dict keys for the hidden Linear layers shift and
    # ``load_state_dict`` raises.
    layers: list[nn.Module] = []
    prev = input_dim
    for h in hidden_dims:
        layers.append(nn.Linear(prev, h))
        layers.append(nn.GELU())
        layers.append(nn.Dropout(p=max(dropout, 0.0)))
        prev = h
    layers.append(nn.Linear(prev, num_classes))
    layers.append(nn.Softplus(beta=1.0))
    return nn.Sequential(*layers)


# ---------------------------------------------------------------------------
# DANN: Gradient Reversal Layer + shared-extractor architecture
# ---------------------------------------------------------------------------


def _grad_reverse_class() -> type:
    """Late-bind torch so importing this module does not require torch."""
    import torch

    class GradientReversalFn(torch.autograd.Function):
        """Forward identity, backward multiplies gradient by ``-alpha``.

        Per Ganin & Lempitsky 2015, this lets the shared feature extractor
        receive a *task-aligned* gradient from the task head and a
        *task-orthogonal* (sign-flipped) gradient from the domain head, so the
        extracted features end up domain-invariant.
        """

        @staticmethod
        def forward(ctx: Any, x: Tensor, alpha: float) -> Tensor:  # type: ignore[override]
            ctx.alpha = float(alpha)
            return x.view_as(x)

        @staticmethod
        def backward(ctx: Any, grad_output: Tensor) -> tuple[Tensor, None]:  # type: ignore[override]
            return -ctx.alpha * grad_output, None

    return GradientReversalFn


def grad_reverse(x: Tensor, alpha: float) -> Tensor:
    """Pass ``x`` through identity in forward, reverse its gradient in backward."""
    fn = _grad_reverse_class()
    return fn.apply(x, alpha)


def build_dann_evidential_model(
    input_dim: int,
    num_classes: int,
    num_domains: int,
    hidden_dims: tuple[int, ...] = (64, 32),
    domain_hidden: int = 32,
    dropout: float = 0.15,
) -> nn.Module:
    """Construct the DANN-augmented Evidential model.

    Architecture identifier: ``dann_v1``. Topology::

        x → [shared feature extractor]
             ├─→ [task head: Linear → Softplus] → evidence (Dirichlet)
             └─→ [GRL(λ)] → [domain head: Linear → GELU → Linear] → domain logits

    The task head matches the ``sequential_v1`` Softplus head so the EDL
    machinery (loss + uncertainty math) is reused unchanged. Inference does NOT
    require the domain head and skips it via ``predict_evidence``.
    """
    from torch import nn

    class DANNEvidentialModel(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            fx_layers: list[nn.Module] = []
            prev = input_dim
            for h in hidden_dims:
                fx_layers.append(nn.Linear(prev, h))
                fx_layers.append(nn.GELU())
                fx_layers.append(nn.Dropout(p=max(dropout, 0.0)))
                prev = h
            self.feature_extractor = nn.Sequential(*fx_layers)
            feature_dim = hidden_dims[-1]
            self.task_head = nn.Sequential(
                nn.Linear(feature_dim, num_classes),
                nn.Softplus(beta=1.0),
            )
            self.domain_head = nn.Sequential(
                nn.Linear(feature_dim, domain_hidden),
                nn.GELU(),
                nn.Linear(domain_hidden, num_domains),
            )

        def forward(
            self, x: torch.Tensor, grl_alpha: float = 1.0
        ) -> tuple[torch.Tensor, torch.Tensor]:
            features = self.feature_extractor(x)
            evidence = self.task_head(features)
            domain_logits = self.domain_head(grad_reverse(features, grl_alpha))
            return evidence, domain_logits

        def predict_evidence(self, x: torch.Tensor) -> torch.Tensor:
            """Inference path — domain head is not consulted."""
            return self.task_head(self.feature_extractor(x))

    return DANNEvidentialModel()


def edl_mse_loss(
    evidence: Tensor,
    target_one_hot: Tensor,
    *,
    epoch: int,
    annealing_epochs: int = 10,
    class_weights: Tensor | None = None,
    focal_gamma: float = 0.0,
) -> Tensor:
    """Sensoy Type-II ML loss with KL annealing, optionally class-weighted +
    focal-style hard-example weighting.

    Baseline (when both extras are off) is the canonical Sensoy 2018 form::

        L = (y − p)^2 + p(1−p)/(S+1) + λ(t) · KL[Dir(α̃) || Dir(1)]

    where ``α̃ = y + (1 − y) · α`` zeroes evidence on the true class so the
    regularizer only punishes misleading off-class evidence.

    Optional extensions:

    * ``class_weights`` — shape ``(K,)`` tensor of per-class scalars (e.g.
      sklearn's "balanced" ``N / (K · n_c)``). Each sample's fit term is
      scaled by ``w[y_i]``, addressing class imbalance.
    * ``focal_gamma`` — Lin et al. 2017 focal-loss adaptation: scale the fit
      term by ``(1 − E[p_{y_i}])^γ``. ``γ = 0`` disables (identity weight);
      ``γ = 1.5–2.0`` strongly down-weights easy examples.

    The KL regularizer is intentionally NOT class-weighted — it serves as a
    distribution-level prior that should apply uniformly so the model does not
    overweight minority classes into a degenerate strength-overflow regime.
    """
    import torch

    alpha = evidence + 1.0
    strength = alpha.sum(dim=-1, keepdim=True)
    expected = alpha / strength

    # First two terms — fit + variance penalty in expectation under the Dirichlet.
    err = (target_one_hot - expected).pow(2).sum(dim=-1)
    # ``strength`` stays as ``(B, 1)`` so it broadcasts against the (B, K) ``expected``.
    var = (expected * (1.0 - expected) / (strength + 1.0)).sum(dim=-1)
    fit = err + var

    # Per-sample weighting — class-balanced and/or focal.
    sample_weight = torch.ones_like(fit)
    if class_weights is not None:
        # E[p] under the true class, used both for focal and reweighting lookups.
        # target_one_hot @ class_weights gives w[y_i] per sample.
        w = (target_one_hot * class_weights.to(target_one_hot.device)).sum(dim=-1)
        sample_weight = sample_weight * w
    if focal_gamma > 0.0:
        p_true = (target_one_hot * expected).sum(dim=-1).clamp(min=1e-7, max=1.0 - 1e-7)
        focal = (1.0 - p_true).pow(focal_gamma)
        sample_weight = sample_weight * focal

    # KL[Dir(alpha_tilde) || Dir(1)] — closed form.
    alpha_tilde = target_one_hot + (1.0 - target_one_hot) * alpha
    k = alpha.shape[-1]
    sum_alpha = alpha_tilde.sum(dim=-1, keepdim=True)
    lgamma = torch.lgamma
    digamma = torch.digamma
    kl = (
        lgamma(sum_alpha).squeeze(-1)
        - lgamma(torch.tensor(float(k), device=alpha.device))
        - lgamma(alpha_tilde).sum(dim=-1)
        + (
            (alpha_tilde - 1.0)
            * (digamma(alpha_tilde) - digamma(sum_alpha))
        ).sum(dim=-1)
    )

    lam = min(1.0, float(epoch) / float(max(1, annealing_epochs)))

    # Normalize sample_weight to keep the loss scale comparable to baseline.
    sw_mean = sample_weight.mean().clamp(min=1e-7)
    weighted_fit = (sample_weight * fit).mean() / sw_mean
    return weighted_fit + lam * kl.mean()
