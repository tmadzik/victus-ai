"""Unit tests for the REDCap/ODK row coercion (no DB)."""

from __future__ import annotations

import pytest

from victus_api.research.importer import ImportRowError, coerce_row, parse_csv
from victus_api.research.schemas import CaptureDomain
from victus_api.triage.schemas import Sex


def _row(**over: str) -> dict[str, str]:
    base = {
        "age": "54",
        "sex": "M",
        "height_cm": "172",
        "weight_kg": "99",
        "waist_cm": "112",
        "systolic_bp": "158",
        "diastolic_bp": "98",
        "hba1c": "7.2",
        "country": "NG",
    }
    base.update(over)
    return base


def test_coerce_valid_row() -> None:
    payload, site = coerce_row(_row())
    assert payload.age_years == 54
    assert payload.sex is Sex.MALE
    assert payload.height_cm == 172.0
    assert payload.systolic_bp_mmhg == 158.0
    assert payload.hba1c_percent == 7.2
    assert payload.capture_domain is CaptureDomain.CLINICAL_GRADE
    assert site == "NG"


def test_header_aliases_and_case_insensitivity() -> None:
    # REDCap-style alias headers + uppercase should still resolve.
    payload, _ = coerce_row(
        {"Age": "40", "Gender": "female", "Height": "160", "Weight": "70",
         "Waist Circumference": "85"}
    )
    assert payload.age_years == 40 and payload.sex is Sex.FEMALE


def test_sentinels_become_none() -> None:
    payload, _ = coerce_row(_row(hba1c="?", systolic_bp="", diastolic_bp=""))
    assert payload.hba1c_percent is None
    assert payload.systolic_bp_mmhg is None


def test_missing_sex_is_row_error() -> None:
    with pytest.raises(ImportRowError, match="sex"):
        coerce_row(_row(sex=""))


def test_non_numeric_is_row_error() -> None:
    with pytest.raises(ImportRowError, match="not a number"):
        coerce_row(_row(weight_kg="heavy"))


def test_half_bp_pair_is_row_error() -> None:
    # Only systolic provided → ResearchCaseCreate's pair validator rejects it.
    with pytest.raises(ImportRowError):
        coerce_row(_row(diastolic_bp=""))


def test_out_of_range_is_row_error() -> None:
    with pytest.raises(ImportRowError):
        coerce_row(_row(age="900"))


def test_parse_csv_reads_rows() -> None:
    text = "age,sex,height_cm,weight_kg,waist_cm\n54,M,172,99,112\n40,F,160,70,85\n"
    rows = parse_csv(text)
    assert len(rows) == 2
    assert rows[0]["sex"] == "M"
