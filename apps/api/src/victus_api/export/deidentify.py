"""De-identification for the training export: what may leave a deployment.

This is the machinery behind the promise made to funders — that Victus receives
data for model training which is not linked to their organisation or to any
individual member.

That promise is not met by the platform's existing anonymisation path, and it is
worth being precise about why. ``governance/anonymiser.py`` is titled "Pure
pseudonymisation helpers" and does exactly that: a salted SHA-256 over the
subject id. The deployment holds the salt, so the mapping is reversible by
anyone holding it together with a candidate list of subjects. Under POPIA, the
NDPA and the Cyber and Data Protection Act that remains personal data. It is the
right tool for erasure-with-continuity; it is the wrong tool for release.

Release needs something different, and this module implements it:

1. **Allowlist projection.** Only fields named in ``ReleaseSpec.release`` are
   emitted. A denylist would fail open — the next column somebody adds to
   ``rppg_calibration_records`` would flow out by default and nobody would
   notice until it had. Fields must be opted *in*, one at a time.
2. **Generalisation.** Quasi-identifiers are coarsened before release: ages into
   bands, with the tail top-coded because "94 years old" identifies a person in
   a way "45–54" does not.
3. **k-anonymity with suppression.** Rows are grouped by their generalised
   quasi-identifier tuple, and any group smaller than *k* is dropped whole. No
   partial release, no "just this once" — a class of one is a person.

What this module does **not** do is make the result provably anonymous. That is
a judgement about a specific dataset and a specific adversary, and it belongs in
a re-identification risk assessment signed by someone accountable, not in code.
See ``ENROLLMENT_DPIA.md`` for the assumptions this implementation makes and the
residual risks it does not close.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

# A class of one is a person; a class of two is a person and the one other
# member, who can therefore identify them. Below this there is no meaningful
# protection at all, so it is a hard floor rather than a default.
K_FLOOR = 2
K_DEFAULT = 5

# Field names that must never be released, whatever a caller asks for. These are
# direct identifiers or the keys that relink them. The check is belt-and-braces
# behind the allowlist: the allowlist is the control, this catches the case
# where someone adds an identifier to the allowlist by mistake.
NEVER_RELEASE = frozenset(
    {
        "id",
        "user_id",
        "subject_id",
        "study_subject_id",
        "toi_assessment_id",
        "study_session_id",
        "organisation_id",
        "org_code",
        "external_subject_id",
        "email",
        "full_name",
        "phone",
        "wa_phone",
        "notes",
        "medical_history_summary",
        "reference_device_label",
        "erasure_request_id",
    }
)


class ReleaseSpecError(ValueError):
    """A release specification that would leak. Raised at construction, not at
    export time, so a bad spec fails in a test rather than in a data transfer."""


@dataclass(frozen=True)
class ReleaseSpec:
    """Declares exactly what a training export may contain.

    ``quasi_identifiers`` are the fields an adversary is assumed to already know
    about a target — age band, sex, site. They define the equivalence classes
    that k-anonymity is computed over, and they must all appear in ``release``.

    ``release`` is the complete allowlist. Anything absent from it is dropped.
    """

    release: frozenset[str]
    quasi_identifiers: tuple[str, ...]
    k: int = K_DEFAULT

    def __post_init__(self) -> None:
        if self.k < K_FLOOR:
            raise ReleaseSpecError(
                f"k={self.k} provides no meaningful protection; the floor is "
                f"{K_FLOOR}. A class of one is a person."
            )
        leaked = self.release & NEVER_RELEASE
        if leaked:
            raise ReleaseSpecError(
                f"These fields are direct identifiers or relinking keys and "
                f"cannot be released: {sorted(leaked)}."
            )
        missing = set(self.quasi_identifiers) - self.release
        if missing:
            raise ReleaseSpecError(
                f"Quasi-identifiers must also be released to be meaningful, but "
                f"{sorted(missing)} are not in the allowlist. k-anonymity would "
                "be computed over a column the recipient never sees."
            )
        if not self.quasi_identifiers:
            raise ReleaseSpecError(
                "A release with no quasi-identifiers cannot be k-anonymised. "
                "If the data genuinely has none, say so explicitly by declaring "
                "a constant field rather than leaving this empty."
            )


@dataclass
class SuppressionReport:
    """What the export withheld, and why.

    Kept and returned rather than logged in passing: a recipient who cannot see
    what was suppressed cannot tell a thin cohort from a biased one, and
    suppression is never uniform — it falls hardest on exactly the small
    subgroups whose representation the fairness analysis depends on.
    """

    rows_in: int = 0
    rows_released: int = 0
    rows_suppressed: int = 0
    classes_released: int = 0
    classes_suppressed: int = 0
    k: int = K_DEFAULT
    smallest_released_class: int | None = None
    suppressed_class_keys: list[tuple[object, ...]] = field(default_factory=list)

    @property
    def suppression_rate(self) -> float:
        return round(self.rows_suppressed / self.rows_in, 4) if self.rows_in else 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "rows_in": self.rows_in,
            "rows_released": self.rows_released,
            "rows_suppressed": self.rows_suppressed,
            "classes_released": self.classes_released,
            "classes_suppressed": self.classes_suppressed,
            "k": self.k,
            "smallest_released_class": self.smallest_released_class,
            "suppression_rate": self.suppression_rate,
        }


def age_band(age: int | None, *, width: int = 10, top_code: int = 80) -> str | None:
    """Coarsen an age into a band, top-coding the tail.

    Top-coding matters more than the band width. Ages are roughly uniform in the
    middle of the range and very sparse at the top, so a 90-year-old is often
    unique in a cohort while a 45-year-old never is. Without a top code the
    oldest participants are re-identifiable no matter how wide the bands are.
    """
    if age is None:
        return None
    if age < 0:
        raise ValueError(f"age must not be negative, got {age}")
    if age >= top_code:
        return f"{top_code}+"
    low = (age // width) * width
    return f"{low}-{low + width - 1}"


def project(row: Mapping[str, object], *, spec: ReleaseSpec) -> dict[str, object]:
    """Keep only the allowlisted fields of ``row``. Everything else is dropped."""
    return {key: row[key] for key in spec.release if key in row}


def _class_key(row: Mapping[str, object], quasi_identifiers: Sequence[str]) -> tuple:
    return tuple(row.get(qi) for qi in quasi_identifiers)


def k_anonymise(
    rows: Iterable[Mapping[str, object]], *, spec: ReleaseSpec
) -> tuple[list[dict[str, object]], SuppressionReport]:
    """Project, group by quasi-identifier tuple, and drop every class below k.

    Suppression is whole-class. Releasing part of an under-sized class would
    leave the released rows in a class of their own, which is the situation k is
    supposed to prevent — so there is no partial release and no override.

    Rows arrive already generalised: this function does not decide how to coarsen
    a field, only whether the resulting classes are large enough to release. That
    separation keeps the policy decision (how coarse) visible at the call site
    instead of buried in here.
    """
    projected = [project(row, spec=spec) for row in rows]

    buckets: dict[tuple, list[dict[str, object]]] = defaultdict(list)
    for row in projected:
        buckets[_class_key(row, spec.quasi_identifiers)].append(row)

    released: list[dict[str, object]] = []
    report = SuppressionReport(rows_in=len(projected), k=spec.k)

    for key, bucket in buckets.items():
        if len(bucket) < spec.k:
            report.classes_suppressed += 1
            report.rows_suppressed += len(bucket)
            report.suppressed_class_keys.append(key)
            continue
        report.classes_released += 1
        released.extend(bucket)
        if (
            report.smallest_released_class is None
            or len(bucket) < report.smallest_released_class
        ):
            report.smallest_released_class = len(bucket)

    report.rows_released = len(released)
    return released, report


# --- aggregate cell suppression ----------------------------------------------
#
# Cohort dashboards publish counts, not rows, and counts leak differently. The
# same k threshold applies — a cell of one is still a person — but suppressing
# small cells is not sufficient on its own, which is what
# :func:`suppress_small_cells` exists to handle.


@dataclass
class CellSuppressionReport:
    k: int
    cells_in: int = 0
    cells_suppressed: int = 0
    complementary_suppressed: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "k": self.k,
            "cells_in": self.cells_in,
            "cells_suppressed": self.cells_suppressed,
            "complementary_suppressed": self.complementary_suppressed,
        }


def suppress_small_cells(
    cells: Mapping[str, int], *, k: int, total_is_published: bool = True
) -> tuple[dict[str, int | None], CellSuppressionReport]:
    """Blank every cell below ``k``, then guard against recovery by subtraction.

    The subtlety is the second step. Suppressing exactly one cell while
    publishing the total does not hide it: the reader subtracts the visible
    cells from the total and recovers the suppressed count exactly. Disclosure
    control calls the fix *complementary suppression* — a second cell has to go
    so the remainder is shared between at least two unknowns.

    The complement chosen is the smallest surviving cell, because blanking the
    smallest destroys the least information while still splitting the residual.

    ``total_is_published=False`` says the caller is withholding the total, which
    removes the subtraction route and makes the complement unnecessary.
    """
    if k < K_FLOOR:
        raise ReleaseSpecError(
            f"k={k} provides no meaningful protection; the floor is {K_FLOOR}."
        )

    report = CellSuppressionReport(k=k, cells_in=len(cells))
    out: dict[str, int | None] = {}
    for label, count in cells.items():
        if 0 < count < k:
            out[label] = None
            report.cells_suppressed += 1
        else:
            out[label] = count

    # A zero cell is not disclosive — "nobody here" names no one — so zeros stay
    # visible and do not count as suppressed. But they also cannot serve as the
    # complement, since blanking a zero hides nothing.
    if total_is_published and report.cells_suppressed == 1:
        candidates = {
            label: value
            for label, value in out.items()
            if value is not None and value > 0
        }
        if candidates:
            smallest = min(candidates, key=lambda label: candidates[label])
            out[smallest] = None
            report.complementary_suppressed = 1

    return out, report
