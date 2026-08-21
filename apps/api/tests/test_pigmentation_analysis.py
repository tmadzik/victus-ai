"""Pigmentation analysis — the continuous ITA° primary and the MST bands.

Validation plan §3.4 makes the *continuous* fit the primary fairness readout and
demotes banding to a pre-specified secondary. These tests pin the properties
that make that claim trustworthy: that a real pigmentation effect is detected
with the right sign, that a flat relationship is not dressed up as one, and that
the fit refuses to speak when the cohort cannot support it.
"""

from __future__ import annotations

from victus_api.calibration.statistics import (
    MONK_BANDS,
    CalibrationPair,
    compute_stratified,
    regress_on_ita,
)


def _pair(
    *,
    ita: float | None,
    error: float,
    mst: int | None = None,
    snr: float | None = None,
) -> CalibrationPair:
    """A pair whose rPPG HR sits ``error`` bpm above a fixed reference."""
    return CalibrationPair(
        rppg_hr_bpm=72.0 + error,
        reference_hr_bpm=72.0,
        quality="GOOD",
        skin_tone=None,
        reference_device_type="ECG_STRAP",
        ita_degrees=ita,
        monk_skin_tone=mst,
        rppg_snr_db=snr,
    )


def test_detects_error_growing_as_skin_darkens() -> None:
    # ITA falls as skin darkens, so an error that grows on darker skin must
    # come back as a NEGATIVE slope. Getting this sign backwards would invert
    # the platform's central equity claim.
    pairs = [_pair(ita=ita, error=(50.0 - ita) * 0.06) for ita in range(-40, 50, 5)]
    fit = regress_on_ita(pairs)

    assert fit is not None
    assert fit.slope < 0
    assert fit.slope_ci_upper < 0  # the CI excludes "no effect"
    assert fit.n == len(pairs)
    assert fit.ita_min == -40.0


def test_flat_relationship_is_not_reported_as_an_effect() -> None:
    # Constant error across the whole pigmentation range: the honest answer is
    # a slope whose interval straddles zero, not a small "significant" number.
    pairs = [_pair(ita=ita, error=2.0) for ita in range(-40, 50, 5)]
    fit = regress_on_ita(pairs)

    assert fit is not None
    assert fit.slope_ci_lower <= 0.0 <= fit.slope_ci_upper


def test_refuses_a_fit_when_every_subject_shares_one_skin_tone() -> None:
    # A regression across subjects who are all the same tone says nothing about
    # tone. Returning a slope here would be worse than returning nothing.
    pairs = [_pair(ita=-35.0, error=e) for e in (1.0, 4.0, 2.0, 6.0, 3.0)]
    assert regress_on_ita(pairs) is None


def test_refuses_a_fit_below_three_measured_pairs() -> None:
    assert regress_on_ita([_pair(ita=-30.0, error=1.0)]) is None
    assert regress_on_ita([]) is None


def test_pairs_without_ita_are_excluded_not_imputed() -> None:
    # Unmeasured pigmentation must drop out of the fairness fit entirely —
    # imputing it would manufacture agreement the study never observed.
    measured = [_pair(ita=ita, error=1.0) for ita in (-40.0, 0.0, 40.0)]
    fit = regress_on_ita([*measured, _pair(ita=None, error=99.0)])

    assert fit is not None
    assert fit.n == 3


def test_snr_measure_uses_snr_and_needs_it_present() -> None:
    pairs = [_pair(ita=ita, error=1.0, snr=(ita + 50.0) * 0.1) for ita in range(-40, 50, 10)]
    fit = regress_on_ita(pairs, measure="snr")

    assert fit is not None
    assert fit.slope > 0  # SNR falls as ITA falls (darker skin, weaker signal)
    # Same pairs with no SNR recorded → no fit, rather than a fit on the error.
    assert regress_on_ita([_pair(ita=p.ita_degrees, error=1.0) for p in pairs],
                          measure="snr") is None


def test_monk_bands_resolve_the_dark_end_and_collapse_the_light() -> None:
    labels = [label for label, _, _ in MONK_BANDS]
    assert labels == ["MST_1_4", "MST_5_6", "MST_7_8", "MST_9_10"]

    # The light band spans four points; every dark band spans two. That
    # asymmetry is the deliberate inversion of Fitzpatrick's shape.
    spans = {label: hi - lo + 1 for label, lo, hi in MONK_BANDS}
    assert spans["MST_1_4"] == 4
    assert all(spans[b] == 2 for b in ("MST_5_6", "MST_7_8", "MST_9_10"))


def test_stratified_emits_bands_and_regressions() -> None:
    pairs = [
        _pair(ita=45.0, error=0.5, mst=2, snr=9.0),
        _pair(ita=30.0, error=1.0, mst=5, snr=8.0),
        _pair(ita=0.0, error=3.0, mst=7, snr=5.0),
        _pair(ita=-40.0, error=6.0, mst=10, snr=2.0),
        _pair(ita=-35.0, error=5.5, mst=9, snr=2.5),
    ]
    stats = compute_stratified(pairs)

    assert stats.ita_error_regression is not None
    assert stats.ita_snr_regression is not None
    assert stats.by_monk_band["MST_9_10"] is not None
    assert stats.by_monk_band["MST_9_10"].n == 2
    # Bands with no subjects are omitted rather than rendered as empty rows.
    assert "MST_1_4" in stats.by_monk_band

    payload = stats.to_dict()
    assert payload["ita_error_regression"]["slope"] < 0
    assert "by_monk_band" in payload
    # Fitzpatrick survives as the recorded secondary.
    assert "by_fitzpatrick" in payload
