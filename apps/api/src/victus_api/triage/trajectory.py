"""Longitudinal risk trajectories — turn a series of point-in-time triage
assessments into a per-disease trend, and decide whether a change is *real* or
just measurement noise using the EDL uncertainty the model already produces.

Why this exists: a single screening answers "are you at risk today?"; the value
for NCDs is "is your risk *moving*, and did the intervention bend the curve?".
Repeated cheap contactless captures make that possible — but only if we can tell
a genuine change from run-to-run noise. That is exactly what evidential
uncertainty (Dirichlet vacuity) is for: a change is only called significant when
its magnitude exceeds the combined uncertainty of its endpoints.

Pure module: no I/O, no DB. The service feeds it stored assessments; it is a
research-demonstrator analytic (like every triage output, it is gated by the
clinical-claims layer at the surface).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from victus_api.triage.schemas import (
    Disease,
    PerDiseaseRisk,
    RiskClass,
    TrajectoryDirection,
    TriageState,
)

# Ordinal severity of each risk class; the risk index is the probability-weighted
# mean ordinal, normalised to [0, 1]. A smooth scalar is far more trendable than
# the discrete GREEN/YELLOW/RED state.
_RISK_ORDINAL: dict[RiskClass, int] = {
    RiskClass.LOW_RISK: 0,
    RiskClass.ELEVATED_RISK: 1,
    RiskClass.HIGH_RISK: 2,
    RiskClass.VERY_HIGH_RISK: 3,
}
_MAX_ORDINAL = 3

# A change is "significant" only when |delta| exceeds this multiple of the mean
# endpoint vacuity — i.e. the move must be larger than the model's own
# uncertainty. Heuristic (not clinically validated), deliberately conservative
# so run-to-run noise does not read as progression.
SIGNIFICANCE_K = 1.0

# Diseases in a stable presentation order for the response.
_DISEASE_ORDER = list(Disease)


@dataclass(frozen=True)
class TrajectoryPoint:
    at: datetime
    risk_index: float
    vacuity: float
    state: TriageState


@dataclass(frozen=True)
class DiseaseTrajectory:
    disease: Disease
    points: list[TrajectoryPoint]
    baseline_index: float
    latest_index: float
    delta: float
    direction: TrajectoryDirection
    change_is_significant: bool
    latest_state: TriageState


@dataclass(frozen=True)
class AssessmentSnapshot:
    """One assessment in time — what the service passes in (ascending by ``at``)."""

    at: datetime
    per_disease: list[PerDiseaseRisk]


def risk_index(class_probabilities: dict[RiskClass, float]) -> float:
    """Probability-weighted mean risk ordinal, normalised to [0, 1]."""
    total = sum(
        prob * _RISK_ORDINAL.get(cls, 0)
        for cls, prob in class_probabilities.items()
    )
    return max(0.0, min(1.0, total / _MAX_ORDINAL))


def _direction(delta: float, significant: bool) -> TrajectoryDirection:
    if not significant:
        return TrajectoryDirection.STABLE
    return TrajectoryDirection.RISING if delta > 0 else TrajectoryDirection.FALLING


def _build_disease_trajectory(
    disease: Disease, points: list[TrajectoryPoint]
) -> DiseaseTrajectory:
    baseline = points[0]
    latest = points[-1]
    delta = latest.risk_index - baseline.risk_index
    # Combined endpoint uncertainty as the noise floor: a change smaller than
    # this is within measurement noise and is not called real.
    noise_band = SIGNIFICANCE_K * (baseline.vacuity + latest.vacuity) / 2.0
    significant = len(points) >= 2 and abs(delta) > noise_band
    return DiseaseTrajectory(
        disease=disease,
        points=points,
        baseline_index=round(baseline.risk_index, 4),
        latest_index=round(latest.risk_index, 4),
        delta=round(delta, 4),
        direction=_direction(delta, significant),
        change_is_significant=significant,
        latest_state=latest.state,
    )


def build_trajectories(
    snapshots: list[AssessmentSnapshot],
) -> list[DiseaseTrajectory]:
    """Per-disease trajectories from time-ordered assessments (ascending by at)."""
    by_disease: dict[Disease, list[TrajectoryPoint]] = {}
    for snap in snapshots:
        for risk in snap.per_disease:
            by_disease.setdefault(risk.disease, []).append(
                TrajectoryPoint(
                    at=snap.at,
                    risk_index=risk_index(risk.class_probabilities),
                    vacuity=risk.uncertainty.vacuity,
                    state=risk.state,
                )
            )
    ordered = sorted(
        by_disease.items(),
        key=lambda kv: _DISEASE_ORDER.index(kv[0]),
    )
    return [_build_disease_trajectory(d, pts) for d, pts in ordered]


def rising_crossings(
    prior: list[AssessmentSnapshot], latest: AssessmentSnapshot
) -> list[Disease]:
    """Diseases that just *crossed* into a significant rise because of ``latest``.

    A crossing is a disease whose trajectory was not RISING over ``prior`` but is
    RISING once ``latest`` is appended — the tipping point, not a rise that was
    already flagged. Empty ``prior`` yields nothing (a single point can't trend).
    """
    if not prior:
        return []
    before = {
        t.disease: t.direction for t in build_trajectories(prior)
    }
    after = build_trajectories([*prior, latest])
    crossings: list[Disease] = []
    for traj in after:
        was_rising = before.get(traj.disease) is TrajectoryDirection.RISING
        if traj.direction is TrajectoryDirection.RISING and not was_rising:
            crossings.append(traj.disease)
    return crossings
