"""Longitudinal vital-sign trajectories for Pathway B (contactless rPPG).

The triage pathway trends a *risk index* and uses EDL Dirichlet vacuity as its
noise floor (:mod:`victus_api.triage.trajectory`). Pathway B has no class
distribution — it produces continuous vital signs — so this module is the TOI
analog: it trends each validated biomarker in its native unit and uses the
measurement's own confidence-interval width as the noise floor. A change is only
called *real* when its magnitude exceeds the combined interval uncertainty of its
endpoints; a change smaller than that is within measurement noise.

Why it exists: the Mobile Clinic Gateway is the primary walk-up capture channel,
and a repeat contactless check is exactly where a rising resting heart rate or
respiratory rate would first show. A single capture answers "what are the vitals
today?"; the value for NCDs is "are they *moving*?".

Scope decisions (deliberately conservative, none clinically validated):
  * Only the validated biomarkers (heart rate, respiratory rate) are trended.
    HRV and the stress index are experimental and are excluded here for the same
    reason they are withheld from participant/clinician surfaces by default.
  * POOR-quality captures are dropped — signal that never cleared the quality
    floor must not be able to manufacture a trend.
  * When a capture carries no confidence interval, a per-biomarker absolute
    noise floor stands in, so a missing interval can never read as zero
    uncertainty (which would make any tiny change "significant").

Pure module: no I/O, no DB. The service feeds it stored assessments; like every
Pathway B output it is a research-demonstrator analytic, gated by the
clinical-claims layer at the surface.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime

from victus_api.toi.schemas import ToiQuality


class ToiBiomarker(str, enum.Enum):
    """The validated, trendable Pathway B biomarkers (native units)."""

    HEART_RATE = "heart_rate"  # bpm
    RESPIRATORY_RATE = "respiratory_rate"  # breaths/min


# Presentation order + human labels for notification copy.
_BIOMARKER_ORDER: list[ToiBiomarker] = list(ToiBiomarker)
BIOMARKER_LABELS: dict[ToiBiomarker, str] = {
    ToiBiomarker.HEART_RATE: "resting heart rate",
    ToiBiomarker.RESPIRATORY_RATE: "respiratory rate",
}

# Per-biomarker absolute noise floor (native units) used when a capture lacks a
# confidence interval, and as a lower bound on the interval-derived floor. Sized
# to typical rPPG-vs-reference agreement so run-to-run scatter does not read as a
# trend. Heuristic, not clinically validated.
_NOISE_FLOOR: dict[ToiBiomarker, float] = {
    ToiBiomarker.HEART_RATE: 3.0,  # bpm
    ToiBiomarker.RESPIRATORY_RATE: 2.0,  # breaths/min
}

# A change is "significant" only when |delta| exceeds this multiple of the mean
# endpoint uncertainty. Mirrors the triage trajectory constant; deliberately
# conservative so measurement noise does not read as progression.
SIGNIFICANCE_K = 1.0

# Captures at or below this quality are excluded from every trajectory.
_EXCLUDED_QUALITY = frozenset({ToiQuality.POOR})


class TrajectoryDirection(str, enum.Enum):
    RISING = "RISING"
    STABLE = "STABLE"
    FALLING = "FALLING"


@dataclass(frozen=True)
class BiomarkerReading:
    """One biomarker measurement with its (optional) confidence interval."""

    value: float
    ci_low: float | None = None
    ci_high: float | None = None


@dataclass(frozen=True)
class ToiSnapshot:
    """One TOI assessment in time — what the service passes in (any order)."""

    at: datetime
    quality: ToiQuality
    readings: dict[ToiBiomarker, BiomarkerReading]


@dataclass(frozen=True)
class TrajectoryPoint:
    at: datetime
    value: float
    uncertainty: float


@dataclass(frozen=True)
class BiomarkerTrajectory:
    biomarker: ToiBiomarker
    points: list[TrajectoryPoint]
    baseline_value: float
    latest_value: float
    delta: float
    direction: TrajectoryDirection
    change_is_significant: bool


def _uncertainty(reading: BiomarkerReading, biomarker: ToiBiomarker) -> float:
    """Half-width of the confidence interval, floored at the per-biomarker noise
    floor. Falls back to the floor when no interval is present."""
    floor = _NOISE_FLOOR[biomarker]
    if reading.ci_low is None or reading.ci_high is None:
        return floor
    half_width = abs(reading.ci_high - reading.ci_low) / 2.0
    return max(floor, half_width)


def _direction(delta: float, significant: bool) -> TrajectoryDirection:
    if not significant:
        return TrajectoryDirection.STABLE
    return TrajectoryDirection.RISING if delta > 0 else TrajectoryDirection.FALLING


def _build_biomarker_trajectory(
    biomarker: ToiBiomarker, points: list[TrajectoryPoint]
) -> BiomarkerTrajectory:
    baseline = points[0]
    latest = points[-1]
    delta = latest.value - baseline.value
    # Combined endpoint uncertainty as the noise floor: a change smaller than
    # this is within measurement noise and is not called real.
    noise_band = SIGNIFICANCE_K * (baseline.uncertainty + latest.uncertainty) / 2.0
    significant = len(points) >= 2 and abs(delta) > noise_band
    return BiomarkerTrajectory(
        biomarker=biomarker,
        points=points,
        baseline_value=round(baseline.value, 3),
        latest_value=round(latest.value, 3),
        delta=round(delta, 3),
        direction=_direction(delta, significant),
        change_is_significant=significant,
    )


def build_toi_trajectories(
    snapshots: list[ToiSnapshot],
) -> list[BiomarkerTrajectory]:
    """Per-biomarker trajectories from time-ordered assessments (ascending by at).

    POOR-quality captures are dropped. A biomarker is only trended over the
    captures in which it is present."""
    usable = [s for s in snapshots if s.quality not in _EXCLUDED_QUALITY]
    by_biomarker: dict[ToiBiomarker, list[TrajectoryPoint]] = {}
    for snap in usable:
        for biomarker, reading in snap.readings.items():
            by_biomarker.setdefault(biomarker, []).append(
                TrajectoryPoint(
                    at=snap.at,
                    value=reading.value,
                    uncertainty=_uncertainty(reading, biomarker),
                )
            )
    ordered = sorted(
        by_biomarker.items(),
        key=lambda kv: _BIOMARKER_ORDER.index(kv[0]),
    )
    return [_build_biomarker_trajectory(b, pts) for b, pts in ordered]


def rising_crossings(
    prior: list[ToiSnapshot], latest: ToiSnapshot
) -> list[ToiBiomarker]:
    """Biomarkers that just *crossed* into a significant rise because of ``latest``.

    A crossing is a biomarker whose trajectory was not RISING over ``prior`` but
    is RISING once ``latest`` is appended — the tipping point, not a rise that was
    already flagged. Empty ``prior`` (or a POOR ``latest``) yields nothing: a
    single point can't trend, and rejected signal can't raise an alert.
    """
    if not prior or latest.quality in _EXCLUDED_QUALITY:
        return []
    before = {
        t.biomarker: t.direction for t in build_toi_trajectories(prior)
    }
    after = build_toi_trajectories([*prior, latest])
    crossings: list[ToiBiomarker] = []
    for traj in after:
        was_rising = before.get(traj.biomarker) is TrajectoryDirection.RISING
        if traj.direction is TrajectoryDirection.RISING and not was_rising:
            crossings.append(traj.biomarker)
    return crossings
