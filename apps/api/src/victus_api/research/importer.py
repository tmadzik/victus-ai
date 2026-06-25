"""REDCap / ODK / CSV → ``research_triage_cases`` import bridge.

The Victus NCD field study (see the Brief) collects on REDCap/ODK, which both
export tabular CSV. This module maps those rows onto :class:`ResearchCaseCreate`
and reuses the console's label auto-derivation, so a field export lands in the
training corpus without manual re-entry. Header matching is alias-tolerant and
blanks/sentinels (``""``, ``?``, ``NA``) become ``None``; each row is validated
independently so one bad row never aborts the batch.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from victus_api.core.exceptions import VictusError
from victus_api.core.logging import get_logger
from victus_api.db.models import User
from victus_api.research.schemas import (
    CaptureDomain,
    ResearchCaseCreate,
    ResearchImportError,
    ResearchImportSummary,
)
from victus_api.research.service import ResearchError, create_research_case
from victus_api.triage.schemas import Sex

log = get_logger(__name__)

# Canonical field → accepted header aliases (compared lowercased + trimmed).
_ALIASES: dict[str, tuple[str, ...]] = {
    "age_years": ("age", "age_years"),
    "sex": ("sex", "gender"),
    "height_cm": ("height", "height_cm"),
    "weight_kg": ("weight", "weight_kg"),
    "waist_cm": ("waist", "waist_cm", "waist_circumference", "waist_circumference_cm"),
    "hip_cm": ("hip", "hip_cm", "hip_circumference"),
    "systolic_bp_mmhg": ("sbp", "systolic", "systolic_bp", "systolic_bp_mmhg", "bp_systolic"),
    "diastolic_bp_mmhg": ("dbp", "diastolic", "diastolic_bp", "diastolic_bp_mmhg", "bp_diastolic"),
    "fasting_glucose_mmol_l": ("fpg", "fasting_glucose", "fasting_glucose_mmol_l"),
    "hba1c_percent": ("hba1c", "hba1c_percent", "a1c"),
    "capture_domain": ("capture_domain", "domain"),
    "site_code": ("site", "site_code", "country"),
}
_SENTINELS = {"", "?", "na", "n/a", "null", "none", "."}
_SEX = {
    "m": Sex.MALE, "male": Sex.MALE, "1": Sex.MALE,
    "f": Sex.FEMALE, "female": Sex.FEMALE, "2": Sex.FEMALE,
    "o": Sex.OTHER, "other": Sex.OTHER, "3": Sex.OTHER,
}


class ImportRowError(VictusError):
    status_code = 422
    error_code = "import_row_error"


def _normalise(raw: dict[str, str]) -> dict[str, str]:
    # Lowercase and fold spaces/hyphens to underscores so headers like
    # "Waist Circumference" or "Fasting-Glucose" match the aliases.
    def _key(k: str) -> str:
        return "_".join((k or "").strip().lower().replace("-", " ").split())

    return {_key(k): (v if v is not None else "") for k, v in raw.items()}


def _lookup(row: dict[str, str], field: str) -> str | None:
    for alias in _ALIASES[field]:
        if alias in row:
            value = row[alias].strip()
            if value.lower() not in _SENTINELS:
                return value
    return None


def _num(row: dict[str, str], field: str) -> float | None:
    raw = _lookup(row, field)
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError as exc:
        raise ImportRowError(f"{field}: '{raw}' is not a number") from exc


def coerce_row(raw: dict[str, str]) -> tuple[ResearchCaseCreate, str | None]:
    """Map one export row to a (payload, site_code). Raises ImportRowError."""
    row = _normalise(raw)

    sex_raw = _lookup(row, "sex")
    if sex_raw is None or sex_raw.lower() not in _SEX:
        raise ImportRowError(f"sex: missing or unrecognised ({sex_raw!r})")

    age = _num(row, "age_years")
    height = _num(row, "height_cm")
    weight = _num(row, "weight_kg")
    waist = _num(row, "waist_cm")
    if None in (age, height, weight, waist):
        raise ImportRowError("age, height, weight and waist are required")

    domain_raw = (_lookup(row, "capture_domain") or "CLINICAL_GRADE").upper()
    try:
        domain = CaptureDomain(domain_raw)
    except ValueError as exc:
        raise ImportRowError(f"capture_domain: unknown value '{domain_raw}'") from exc

    try:
        payload = ResearchCaseCreate(
            age_years=int(age),  # type: ignore[arg-type]
            sex=_SEX[sex_raw.lower()],
            height_cm=height,  # type: ignore[arg-type]
            weight_kg=weight,  # type: ignore[arg-type]
            waist_cm=waist,  # type: ignore[arg-type]
            hip_cm=_num(row, "hip_cm"),
            systolic_bp_mmhg=_num(row, "systolic_bp_mmhg"),
            diastolic_bp_mmhg=_num(row, "diastolic_bp_mmhg"),
            fasting_glucose_mmol_l=_num(row, "fasting_glucose_mmol_l"),
            hba1c_percent=_num(row, "hba1c_percent"),
            capture_domain=domain,
        )
    except ValueError as exc:
        # Pydantic validation (ranges, BP pairing) → a per-row error.
        raise ImportRowError(str(exc)) from exc

    return payload, _lookup(row, "site_code")


def parse_csv(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text)))


async def import_rows(
    db: AsyncSession,
    *,
    raw_rows: Iterable[dict[str, str]],
    created_by: User,
) -> ResearchImportSummary:
    """Import field-study rows; returns a per-row success/failure summary."""
    imported = 0
    errors: list[ResearchImportError] = []
    for index, raw in enumerate(raw_rows):
        try:
            payload, site_code = coerce_row(raw)
            await create_research_case(
                db, payload=payload, created_by=created_by, site_code=site_code
            )
            imported += 1
        except (ImportRowError, ResearchError) as exc:
            errors.append(ResearchImportError(row=index, error=str(exc)))
    log.info("research_import_done", imported=imported, failed=len(errors))
    return ResearchImportSummary(
        imported=imported, failed=len(errors), errors=errors
    )
