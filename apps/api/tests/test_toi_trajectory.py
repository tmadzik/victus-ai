"""Unit tests for the Pathway B (TOI) longitudinal trajectory detector.

Pure module, no DB: exercises the confidence-interval noise floor, the
crossing-detection semantics, and the quality/empty-prior guards.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from victus_api.toi.schemas import ToiQuality
from victus_api.toi.trajectory import (
    BiomarkerReading,
    ToiBiomarker,
    ToiSnapshot,
    TrajectoryDirection,
    build_toi_trajectories,
    rising_crossings,
)

_T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _snap(
    i: int,
    *,
    hr: float | None = None,
    hr_ci: tuple[float, float] | None = None,
    rr: float | None = None,
    rr_ci: tuple[float, float] | None = None,
    quality: ToiQuality = ToiQuality.GOOD,
) -> ToiSnapshot:
    readings: dict[ToiBiomarker, BiomarkerReading] = {}
    if hr is not None:
        lo, hi = hr_ci if hr_ci is not None else (None, None)
        readings[ToiBiomarker.HEART_RATE] = BiomarkerReading(hr, lo, hi)
    if rr is not None:
        lo, hi = rr_ci if rr_ci is not None else (None, None)
        readings[ToiBiomarker.RESPIRATORY_RATE] = BiomarkerReading(rr, lo, hi)
    return ToiSnapshot(
        at=_T0 + timedelta(minutes=i), quality=quality, readings=readings
    )


def test_rising_crossing_detected_when_hr_tips_up() -> None:
    prior = [_snap(0, hr=60.0, hr_ci=(58.0, 62.0))]
    latest = _snap(1, hr=90.0, hr_ci=(88.0, 92.0))
    assert rising_crossings(prior, latest) == [ToiBiomarker.HEART_RATE]


def test_no_crossing_when_already_rising() -> None:
    # Two prior points already establish a significant rise; the third continues
    # it — a rise that was already flagged is not a fresh crossing.
    prior = [
        _snap(0, hr=60.0, hr_ci=(58.0, 62.0)),
        _snap(1, hr=90.0, hr_ci=(88.0, 92.0)),
    ]
    latest = _snap(2, hr=120.0, hr_ci=(118.0, 122.0))
    assert rising_crossings(prior, latest) == []


def test_no_crossing_when_change_is_within_noise() -> None:
    # Wide intervals → a large noise band; a small move stays STABLE.
    prior = [_snap(0, hr=60.0, hr_ci=(45.0, 75.0))]
    latest = _snap(1, hr=64.0, hr_ci=(49.0, 79.0))
    assert rising_crossings(prior, latest) == []


def test_missing_interval_uses_absolute_floor_not_zero() -> None:
    # No CI → the per-biomarker floor (3 bpm) stands in, so a 2 bpm wobble is
    # noise but a 30 bpm jump is real.
    assert rising_crossings([_snap(0, hr=60.0)], _snap(1, hr=62.0)) == []
    assert rising_crossings([_snap(0, hr=60.0)], _snap(1, hr=90.0)) == [
        ToiBiomarker.HEART_RATE
    ]


def test_empty_prior_never_crosses() -> None:
    assert rising_crossings([], _snap(0, hr=90.0, hr_ci=(88.0, 92.0))) == []


def test_poor_latest_never_crosses() -> None:
    prior = [_snap(0, hr=60.0, hr_ci=(58.0, 62.0))]
    latest = _snap(1, hr=95.0, hr_ci=(93.0, 97.0), quality=ToiQuality.POOR)
    assert rising_crossings(prior, latest) == []


def test_poor_history_is_dropped_from_the_trend() -> None:
    # A POOR mid-capture with an extreme value must not seed a false baseline.
    snaps = [
        _snap(0, hr=60.0, hr_ci=(58.0, 62.0)),
        _snap(1, hr=200.0, hr_ci=(198.0, 202.0), quality=ToiQuality.POOR),
        _snap(2, hr=61.0, hr_ci=(59.0, 63.0)),
    ]
    trajs = {t.biomarker: t for t in build_toi_trajectories(snaps)}
    hr = trajs[ToiBiomarker.HEART_RATE]
    assert len(hr.points) == 2  # the POOR point was excluded
    assert hr.direction is TrajectoryDirection.STABLE


def test_falling_is_not_a_rising_crossing() -> None:
    prior = [_snap(0, hr=90.0, hr_ci=(88.0, 92.0))]
    latest = _snap(1, hr=60.0, hr_ci=(58.0, 62.0))
    assert rising_crossings(prior, latest) == []


def test_respiratory_rate_crosses_independently() -> None:
    prior = [_snap(0, hr=66.0, hr_ci=(64.0, 68.0), rr=14.0, rr_ci=(13.0, 15.0))]
    latest = _snap(1, hr=66.0, hr_ci=(64.0, 68.0), rr=26.0, rr_ci=(25.0, 27.0))
    assert rising_crossings(prior, latest) == [ToiBiomarker.RESPIRATORY_RATE]


def test_build_reports_baseline_latest_and_delta() -> None:
    snaps = [
        _snap(0, hr=60.0, hr_ci=(58.0, 62.0)),
        _snap(1, hr=90.0, hr_ci=(88.0, 92.0)),
    ]
    hr = build_toi_trajectories(snaps)[0]
    assert hr.baseline_value == 60.0
    assert hr.latest_value == 90.0
    assert hr.delta == 30.0
    assert hr.direction is TrajectoryDirection.RISING
    assert hr.change_is_significant is True
