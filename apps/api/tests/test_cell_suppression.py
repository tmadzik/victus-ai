"""Small-cell suppression for cohort dashboards.

Counts leak differently from rows. A breakdown cell containing one person
discloses that person to anyone who knows roughly who is in the cohort — and a
funder knows its own membership exactly, which makes small cells *more*
disclosive on this dashboard than in a public statistical release, not less.

The case worth testing hardest is the second-order one: suppressing a single
cell while publishing the total hides nothing, because the reader subtracts.
"""

from __future__ import annotations

import pytest

from victus_api.export.deidentify import (
    ReleaseSpecError,
    suppress_small_cells,
)


def test_cells_below_k_are_blanked() -> None:
    out, report = suppress_small_cells(
        {"GREEN": 40, "YELLOW": 12, "RED": 2}, k=5, total_is_published=False
    )
    assert out["RED"] is None
    assert out["GREEN"] == 40
    assert report.cells_suppressed == 1


def test_a_cell_exactly_at_k_survives() -> None:
    out, _ = suppress_small_cells({"A": 5, "B": 30}, k=5, total_is_published=False)
    assert out["A"] == 5


def test_a_lone_suppressed_cell_is_recoverable_by_subtraction_so_a_second_goes() -> None:
    # The whole point. With the total published, blanking only RED leaves
    # RED = total − GREEN − YELLOW. A second cell must go so the residual is
    # shared between two unknowns.
    out, report = suppress_small_cells(
        {"GREEN": 40, "YELLOW": 12, "RED": 2}, k=5, total_is_published=True
    )

    suppressed = [label for label, value in out.items() if value is None]
    assert len(suppressed) == 2
    assert "RED" in suppressed
    assert report.complementary_suppressed == 1


def test_the_complement_is_the_smallest_survivor() -> None:
    # Blanking the smallest destroys the least information while still
    # splitting the residual between two unknowns.
    out, _ = suppress_small_cells(
        {"BIG": 100, "MID": 40, "SMALL": 9, "TINY": 1}, k=5, total_is_published=True
    )
    assert out["TINY"] is None
    assert out["SMALL"] is None
    assert out["MID"] == 40
    assert out["BIG"] == 100


def test_no_complement_is_needed_when_two_cells_already_went() -> None:
    # Two unknowns already share the residual; blanking a third would cost
    # information for no gain.
    out, report = suppress_small_cells(
        {"A": 40, "B": 3, "C": 2}, k=5, total_is_published=True
    )
    assert len([v for v in out.values() if v is None]) == 2
    assert report.complementary_suppressed == 0


def test_withholding_the_total_removes_the_need_for_a_complement() -> None:
    out, report = suppress_small_cells(
        {"A": 40, "B": 2}, k=5, total_is_published=False
    )
    assert out["A"] == 40
    assert out["B"] is None
    assert report.complementary_suppressed == 0


def test_zero_cells_stay_visible_and_are_not_treated_as_disclosive() -> None:
    # "Nobody is in this category" names no one. Blanking zeros would also make
    # the dashboard unreadable, since empty categories are common.
    out, report = suppress_small_cells(
        {"GREEN": 40, "YELLOW": 20, "RED": 0}, k=5, total_is_published=True
    )
    assert out["RED"] == 0
    assert report.cells_suppressed == 0
    assert report.complementary_suppressed == 0


def test_a_zero_is_never_chosen_as_the_complement() -> None:
    # Blanking a zero would satisfy a naive "suppress a second cell" rule while
    # hiding nothing at all — the residual would still resolve exactly.
    out, _ = suppress_small_cells(
        {"A": 40, "B": 0, "C": 2}, k=5, total_is_published=True
    )
    assert out["C"] is None
    assert out["B"] == 0  # untouched
    assert out["A"] is None  # the real complement


def test_everything_suppressed_when_the_whole_cohort_is_tiny() -> None:
    out, report = suppress_small_cells(
        {"A": 1, "B": 2}, k=5, total_is_published=True
    )
    assert all(v is None for v in out.values())
    assert report.cells_suppressed == 2


def test_k_below_the_floor_is_refused_here_too() -> None:
    with pytest.raises(ReleaseSpecError):
        suppress_small_cells({"A": 1}, k=1)


def test_empty_input_is_handled() -> None:
    out, report = suppress_small_cells({}, k=5)
    assert out == {}
    assert report.cells_in == 0
