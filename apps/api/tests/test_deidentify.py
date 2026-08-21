"""De-identification — the machinery behind the promise made to funders.

The claim being sold is that Victus receives training data not linked to the
organisation or to any individual member. These tests pin the properties that
have to hold for that to be true, and the failure modes that would make it
quietly false: an allowlist that fails open, a small class released anyway, a
free-text field riding along, a suppression rate nobody can see.
"""

from __future__ import annotations

import pytest

from victus_api.export.deidentify import (
    K_FLOOR,
    NEVER_RELEASE,
    ReleaseSpec,
    ReleaseSpecError,
    age_band,
    k_anonymise,
    project,
)

QI = ("age_band", "sex")


def _spec(k: int = 2, extra: set[str] | None = None) -> ReleaseSpec:
    return ReleaseSpec(
        release=frozenset({"age_band", "sex", "hr"} | (extra or set())),
        quasi_identifiers=QI,
        k=k,
    )


def _rows(n: int, *, band: str = "30-39", sex: str = "FEMALE") -> list[dict]:
    return [{"age_band": band, "sex": sex, "hr": 70.0 + i} for i in range(n)]


# --- the allowlist ------------------------------------------------------------


def test_fields_outside_the_allowlist_are_dropped() -> None:
    # The core property. A denylist would fail open the moment somebody adds a
    # column to rppg_calibration_records; this fails closed.
    row = {
        "age_band": "30-39",
        "sex": "MALE",
        "hr": 72.0,
        "user_id": "u-1",
        "notes": "seen at the depot",
    }
    out = project(row, spec=_spec())

    assert out == {"age_band": "30-39", "sex": "MALE", "hr": 72.0}
    assert "user_id" not in out
    assert "notes" not in out


def test_a_new_column_does_not_leak_by_default() -> None:
    # Simulates someone adding a field to the source table later and not
    # thinking about the export. It must not appear until opted in.
    row = {"age_band": "30-39", "sex": "MALE", "hr": 72.0, "member_number": "MBR-99812"}
    assert "member_number" not in project(row, spec=_spec())


def test_direct_identifiers_are_rejected_even_if_someone_allowlists_them() -> None:
    # Belt-and-braces behind the allowlist: the mistake being caught is a human
    # adding an identifier to the release set on purpose.
    for identifier in ("user_id", "external_subject_id", "email", "organisation_id"):
        with pytest.raises(ReleaseSpecError, match="direct identifiers"):
            ReleaseSpec(
                release=frozenset({"age_band", "sex", identifier}),
                quasi_identifiers=QI,
            )


def test_free_text_can_never_be_released() -> None:
    # No amount of k-anonymity over structured columns helps if a note says
    # "the nurse's cousin".
    assert "notes" in NEVER_RELEASE
    assert "medical_history_summary" in NEVER_RELEASE
    assert "reference_device_label" in NEVER_RELEASE


def test_a_spec_that_would_leak_fails_at_construction_not_at_export() -> None:
    # So a bad release spec breaks a test run rather than a data transfer.
    with pytest.raises(ReleaseSpecError):
        ReleaseSpec(release=frozenset({"user_id"}), quasi_identifiers=("user_id",))


# --- k floor ------------------------------------------------------------------


def test_k_below_the_floor_is_refused() -> None:
    with pytest.raises(ReleaseSpecError, match="class of one is a person"):
        _spec(k=1)
    with pytest.raises(ReleaseSpecError):
        _spec(k=0)


def test_quasi_identifiers_must_themselves_be_released() -> None:
    # k-anonymity computed over a column the recipient never receives is
    # theatre: it constrains nothing about what they can actually join on.
    with pytest.raises(ReleaseSpecError, match="not in the allowlist"):
        ReleaseSpec(
            release=frozenset({"hr", "age_band"}),
            quasi_identifiers=("age_band", "sex"),
        )


# --- k-anonymity and suppression ---------------------------------------------


def test_a_class_smaller_than_k_is_suppressed_whole() -> None:
    rows = _rows(5, sex="FEMALE") + _rows(2, sex="MALE")
    released, report = k_anonymise(rows, spec=_spec(k=5))

    assert report.rows_released == 5
    assert report.rows_suppressed == 2
    assert {r["sex"] for r in released} == {"FEMALE"}
    assert report.classes_suppressed == 1


def test_suppression_is_all_or_nothing() -> None:
    # Releasing part of an under-sized class would leave those rows in a class
    # of their own — precisely what k exists to prevent.
    released, report = k_anonymise(_rows(4), spec=_spec(k=5))
    assert released == []
    assert report.rows_released == 0
    assert report.rows_suppressed == 4


def test_a_class_exactly_at_k_is_released() -> None:
    _, report = k_anonymise(_rows(5), spec=_spec(k=5))
    assert report.rows_released == 5
    assert report.smallest_released_class == 5


def test_every_released_class_is_at_least_k() -> None:
    # The invariant, stated directly rather than inferred from counts.
    rows = _rows(7, band="20-29") + _rows(3, band="40-49") + _rows(11, band="60-69")
    released, report = k_anonymise(rows, spec=_spec(k=5))

    counts: dict[tuple, int] = {}
    for r in released:
        key = (r["age_band"], r["sex"])
        counts[key] = counts.get(key, 0) + 1
    assert counts and all(n >= 5 for n in counts.values())
    assert report.smallest_released_class == 7


def test_a_unique_individual_never_survives() -> None:
    # One person with an unusual combination is the canonical re-identification
    # target, and the one the whole mechanism exists for.
    rows = [*_rows(20), {"age_band": "80+", "sex": "MALE", "hr": 61.0}]
    released, _ = k_anonymise(rows, spec=_spec(k=5))
    assert all(r["age_band"] != "80+" for r in released)


def test_missing_quasi_identifiers_form_their_own_class_and_are_not_a_bypass() -> None:
    # A NULL age must not act as a wildcard that joins every class; it is its
    # own equivalence class and is suppressed like any other if too small.
    rows = [*_rows(6), {"age_band": None, "sex": "FEMALE", "hr": 80.0}]
    released, report = k_anonymise(rows, spec=_spec(k=5))

    assert report.rows_suppressed == 1
    assert all(r["age_band"] is not None for r in released)


# --- the suppression report ---------------------------------------------------


def test_the_report_makes_suppression_visible() -> None:
    # Suppression is never uniform — it falls hardest on the small subgroups the
    # fairness analysis depends on. A recipient who cannot see how much was
    # withheld cannot tell a thin cohort from a biased one.
    rows = _rows(10, band="30-39") + _rows(2, band="80+")
    _, report = k_anonymise(rows, spec=_spec(k=5))

    payload = report.to_dict()
    assert payload["rows_in"] == 12
    assert payload["rows_released"] == 10
    assert payload["rows_suppressed"] == 2
    assert payload["suppression_rate"] == round(2 / 12, 4)
    assert payload["k"] == 5


def test_report_on_an_empty_corpus_does_not_divide_by_zero() -> None:
    released, report = k_anonymise([], spec=_spec(k=5))
    assert released == []
    assert report.suppression_rate == 0.0
    assert report.smallest_released_class is None


# --- generalisation -----------------------------------------------------------


def test_age_is_banded() -> None:
    assert age_band(34) == "30-39"
    assert age_band(30) == "30-39"
    assert age_band(39) == "30-39"
    assert age_band(40) == "40-49"


def test_the_age_tail_is_top_coded() -> None:
    # Ages are dense in the middle and sparse at the top, so a 94-year-old is
    # often unique in a cohort while a 45-year-old never is. Without a top code
    # the oldest participants stay identifiable at any band width.
    assert age_band(80) == "80+"
    assert age_band(94) == "80+"
    assert age_band(112) == "80+"


def test_age_band_passes_through_missing_and_rejects_impossible() -> None:
    assert age_band(None) is None
    with pytest.raises(ValueError, match="negative"):
        age_band(-1)


def test_k_floor_is_two_not_one() -> None:
    assert K_FLOOR == 2
