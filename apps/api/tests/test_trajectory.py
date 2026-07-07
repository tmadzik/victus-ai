"""Longitudinal trajectory analysis — pure, no DB."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from victus_api.triage.schemas import (
    Disease,
    PerDiseaseRisk,
    RiskClass,
    TrajectoryDirection,
    TriageState,
)
from victus_api.triage.trajectory import (
    AssessmentSnapshot,
    build_trajectories,
    risk_index,
)

_BASE = datetime(2026, 1, 1, tzinfo=UTC)


def _risk(disease: Disease, *, vacuity: float, probs: dict[RiskClass, float]) -> PerDiseaseRisk:
    from victus_api.triage.schemas import TriageUncertainty

    top = max(probs, key=lambda k: probs[k])
    return PerDiseaseRisk(
        disease=disease,
        state=TriageState.YELLOW,
        top_class=top,
        class_probabilities=probs,
        evidence={k: v * 10 for k, v in probs.items()},
        uncertainty=TriageUncertainty(
            vacuity=vacuity, aleatoric=0.1, epistemic=0.1, strength=10.0
        ),
        contributing_factors=[],
        next_action="clinician_review",
    )


def _snap(day: int, risk: PerDiseaseRisk) -> AssessmentSnapshot:
    return AssessmentSnapshot(at=_BASE + timedelta(days=day), per_disease=[risk])


_LOW = {
    RiskClass.LOW_RISK: 0.9,
    RiskClass.ELEVATED_RISK: 0.1,
    RiskClass.HIGH_RISK: 0.0,
    RiskClass.VERY_HIGH_RISK: 0.0,
}
_HIGH = {
    RiskClass.LOW_RISK: 0.0,
    RiskClass.ELEVATED_RISK: 0.0,
    RiskClass.HIGH_RISK: 0.1,
    RiskClass.VERY_HIGH_RISK: 0.9,
}


def test_risk_index_bounds() -> None:
    assert risk_index({RiskClass.LOW_RISK: 1.0}) == 0.0
    assert risk_index({RiskClass.VERY_HIGH_RISK: 1.0}) == 1.0
    assert 0.0 < risk_index(_LOW) < 0.2


def test_significant_rise_is_flagged_when_it_beats_the_noise() -> None:
    # Low vacuity (confident) endpoints → a big move is real.
    trajs = build_trajectories(
        [
            _snap(0, _risk(Disease.DIABETES, vacuity=0.05, probs=_LOW)),
            _snap(30, _risk(Disease.DIABETES, vacuity=0.05, probs=_HIGH)),
        ]
    )
    assert len(trajs) == 1
    t = trajs[0]
    assert t.direction is TrajectoryDirection.RISING
    assert t.change_is_significant is True
    assert t.delta > 0
    assert t.latest_index > t.baseline_index


def test_same_move_is_noise_when_uncertainty_is_high() -> None:
    # Identical risk move, but high vacuity → within measurement noise, so STABLE.
    trajs = build_trajectories(
        [
            _snap(0, _risk(Disease.DIABETES, vacuity=0.95, probs=_LOW)),
            _snap(30, _risk(Disease.DIABETES, vacuity=0.95, probs=_HIGH)),
        ]
    )
    t = trajs[0]
    assert t.change_is_significant is False
    assert t.direction is TrajectoryDirection.STABLE


def test_falling_trajectory() -> None:
    trajs = build_trajectories(
        [
            _snap(0, _risk(Disease.DIABETES, vacuity=0.05, probs=_HIGH)),
            _snap(30, _risk(Disease.DIABETES, vacuity=0.05, probs=_LOW)),
        ]
    )
    t = trajs[0]
    assert t.direction is TrajectoryDirection.FALLING
    assert t.change_is_significant is True
    assert t.delta < 0


def test_single_point_is_stable_and_not_significant() -> None:
    trajs = build_trajectories(
        [_snap(0, _risk(Disease.DIABETES, vacuity=0.1, probs=_HIGH))]
    )
    t = trajs[0]
    assert len(t.points) == 1
    assert t.change_is_significant is False
    assert t.direction is TrajectoryDirection.STABLE
    assert t.delta == 0.0


def test_empty_input_yields_no_trajectories() -> None:
    assert build_trajectories([]) == []


# --- rising crossings (the nudge trigger) ------------------------------------

from victus_api.triage.trajectory import rising_crossings  # noqa: E402


def _rising_snap(day: int, disease: Disease, vac: float, probs) -> AssessmentSnapshot:
    return _snap(day, _risk(disease, vacuity=vac, probs=probs))


def test_rising_crossing_detected_when_new_point_tips_it_up() -> None:
    prior = [
        _rising_snap(0, Disease.DIABETES, 0.05, _LOW),
        _rising_snap(10, Disease.DIABETES, 0.05, _LOW),
    ]
    latest = _snap(20, _risk(Disease.DIABETES, vacuity=0.05, probs=_HIGH))
    assert rising_crossings(prior, latest) == [Disease.DIABETES]


def test_no_crossing_when_already_rising() -> None:
    # Already rising over prior → the new point is not a fresh crossing.
    prior = [
        _rising_snap(0, Disease.DIABETES, 0.05, _LOW),
        _rising_snap(10, Disease.DIABETES, 0.05, _HIGH),
    ]
    latest = _snap(20, _risk(Disease.DIABETES, vacuity=0.05, probs=_HIGH))
    assert rising_crossings(prior, latest) == []


def test_no_crossing_when_change_is_noise() -> None:
    # High uncertainty → the move is within noise → not a rise.
    prior = [_rising_snap(0, Disease.DIABETES, 0.95, _LOW)]
    latest = _snap(20, _risk(Disease.DIABETES, vacuity=0.95, probs=_HIGH))
    assert rising_crossings(prior, latest) == []


def test_no_crossing_with_empty_prior() -> None:
    latest = _snap(0, _risk(Disease.DIABETES, vacuity=0.05, probs=_HIGH))
    assert rising_crossings([], latest) == []
