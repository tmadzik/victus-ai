"""Research-console service: derive ground-truth labels, persist, summarise.

Label policy
------------
* **Obesity** — objective from measured BMI (WHO bands).
* **Hypertension** — objective from measured BP (ACC/AHA); refused without a
  reading unless overridden.
* **Diabetes** — anchored on HbA1c (preferred) or fasting plasma glucose (ADA);
  refused without a marker unless overridden. This is the ground truth the
  proxy-only model cannot see.

A clinician may override any derived label; the basis string records which.
"""

from __future__ import annotations

import uuid
from collections import Counter

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from victus_api.core.exceptions import VictusError
from victus_api.core.logging import get_logger
from victus_api.db.models import (
    ResearchTriageCase,
    RiskClass,
    TriageAssessment,
    User,
)
from victus_api.research.schemas import (
    AcquisitionWorklistItem,
    LabelDistribution,
    ResearchCaseCreate,
    ResearchCaseResponse,
    ResearchCorpusStats,
)
from victus_api.triage.acquisition import AcquisitionPriority, score_assessment
from victus_api.triage.schemas import PerDiseaseRisk

log = get_logger(__name__)

_DerivedLabel = tuple[RiskClass | None, str]


class ResearchError(VictusError):
    status_code = 422
    error_code = "research_error"


def _bmi(height_cm: float, weight_kg: float) -> float:
    return weight_kg / ((height_cm / 100.0) ** 2)


def _derive_obesity(bmi: float) -> _DerivedLabel:
    if bmi >= 40.0:
        return RiskClass.VERY_HIGH_RISK, f"BMI {bmi:.1f} — obesity class III"
    if bmi >= 30.0:
        return RiskClass.HIGH_RISK, f"BMI {bmi:.1f} — obesity (class I–II)"
    if bmi >= 25.0:
        return RiskClass.ELEVATED_RISK, f"BMI {bmi:.1f} — overweight"
    if bmi >= 18.5:
        return RiskClass.LOW_RISK, f"BMI {bmi:.1f} — healthy range"
    return RiskClass.LOW_RISK, f"BMI {bmi:.1f} — underweight"


def _derive_hypertension(sys: float | None, dia: float | None) -> _DerivedLabel:
    if sys is None or dia is None:
        return None, ""
    if sys >= 180.0 or dia >= 120.0:
        return RiskClass.VERY_HIGH_RISK, f"BP {sys:.0f}/{dia:.0f} — hypertensive crisis"
    if sys >= 140.0 or dia >= 90.0:
        return RiskClass.HIGH_RISK, f"BP {sys:.0f}/{dia:.0f} — stage 2 hypertension"
    if sys >= 130.0 or dia >= 80.0:
        return RiskClass.ELEVATED_RISK, f"BP {sys:.0f}/{dia:.0f} — stage 1 hypertension"
    return RiskClass.LOW_RISK, f"BP {sys:.0f}/{dia:.0f} — normal"


def _derive_diabetes(hba1c: float | None, fpg: float | None) -> _DerivedLabel:
    # ADA cut-points; prefer HbA1c, fall back to fasting plasma glucose (mmol/L).
    if hba1c is not None:
        if hba1c >= 9.0:
            return RiskClass.VERY_HIGH_RISK, f"HbA1c {hba1c:.1f}% — diabetes, poorly controlled"
        if hba1c >= 6.5:
            return RiskClass.HIGH_RISK, f"HbA1c {hba1c:.1f}% — diabetes"
        if hba1c >= 5.7:
            return RiskClass.ELEVATED_RISK, f"HbA1c {hba1c:.1f}% — prediabetes"
        return RiskClass.LOW_RISK, f"HbA1c {hba1c:.1f}% — normal"
    if fpg is not None:
        if fpg >= 13.9:
            return (
                RiskClass.VERY_HIGH_RISK,
                f"FPG {fpg:.1f} mmol/L — diabetes, marked hyperglycaemia",
            )
        if fpg >= 7.0:
            return RiskClass.HIGH_RISK, f"FPG {fpg:.1f} mmol/L — diabetes"
        if fpg >= 5.6:
            return RiskClass.ELEVATED_RISK, f"FPG {fpg:.1f} mmol/L — prediabetes"
        return RiskClass.LOW_RISK, f"FPG {fpg:.1f} mmol/L — normal"
    return None, ""


_HBA1C_VARIANT_CAVEAT = (
    "HbA1c can be unreliable where haemoglobin variants (HbS / HbC, common in "
    "West Africa) are present — corroborate with fasting glucose or an OGTT."
)


def _diabetes_caveat(
    hba1c: float | None, fpg: float | None, override: RiskClass | None
) -> str | None:
    """Flag (do not change) a diabetes label that leans on HbA1c in a population
    where haemoglobin variants distort it. Returns a caveat string or None."""
    if override is not None or hba1c is None:
        return None
    if fpg is None:
        # HbA1c is the sole marker — no glucose corroboration.
        return _HBA1C_VARIANT_CAVEAT
    # Both present: surface a discordance the HbA1c-preferring derivation hides.
    hb_cat, _ = _derive_diabetes(hba1c, None)
    fpg_cat, _ = _derive_diabetes(None, fpg)
    if hb_cat is not None and fpg_cat is not None and hb_cat != fpg_cat:
        return (
            f"HbA1c and fasting glucose disagree ({hb_cat.value} vs "
            f"{fpg_cat.value}) — consider an OGTT / repeat; HbA1c may be "
            "confounded by haemoglobin variants."
        )
    return None


def _resolve(
    override: RiskClass | None, derived: _DerivedLabel, *, missing_msg: str
) -> tuple[RiskClass, str]:
    if override is not None:
        return override, "clinician-set"
    label, basis = derived
    if label is None:
        raise ResearchError(missing_msg)
    return label, basis


async def create_research_case(
    db: AsyncSession,
    *,
    payload: ResearchCaseCreate,
    created_by: User,
    site_code: str | None = None,
    source_triage_assessment_id: uuid.UUID | None = None,
) -> ResearchCaseResponse:
    bmi = _bmi(payload.height_cm, payload.weight_kg)
    basis: dict[str, str] = {}

    obesity, basis["obesity"] = _resolve(
        payload.obesity_label, _derive_obesity(bmi), missing_msg=""
    )
    hypertension, basis["hypertension"] = _resolve(
        payload.hypertension_label,
        _derive_hypertension(payload.systolic_bp_mmhg, payload.diastolic_bp_mmhg),
        missing_msg="Hypertension label needs a blood-pressure reading or an explicit override.",
    )
    diabetes, basis["diabetes"] = _resolve(
        payload.diabetes_label,
        _derive_diabetes(payload.hba1c_percent, payload.fasting_glucose_mmol_l),
        missing_msg="Diabetes label needs HbA1c or fasting glucose, or an explicit override.",
    )
    caveat = _diabetes_caveat(
        payload.hba1c_percent, payload.fasting_glucose_mmol_l, payload.diabetes_label
    )
    if caveat:
        basis["diabetes_caveat"] = caveat

    row = ResearchTriageCase(
        created_by_user_id=created_by.id,
        study_subject_id=payload.study_subject_id,
        source_triage_assessment_id=source_triage_assessment_id,
        capture_domain=payload.capture_domain.value,
        # Imported field-study rows carry their own site (the study spans SA+NG);
        # interactive console entries default to the creator's deployment site.
        site_code=site_code or created_by.site_code,
        age_years=payload.age_years,
        sex=payload.sex.value,
        height_cm=payload.height_cm,
        weight_kg=payload.weight_kg,
        waist_cm=payload.waist_cm,
        hip_cm=payload.hip_cm,
        systolic_bp_mmhg=payload.systolic_bp_mmhg,
        diastolic_bp_mmhg=payload.diastolic_bp_mmhg,
        safety_triggers=list(payload.safety_triggers),
        contextual=list(payload.contextual),
        fasting_glucose_mmol_l=payload.fasting_glucose_mmol_l,
        hba1c_percent=payload.hba1c_percent,
        obesity_label=obesity,
        hypertension_label=hypertension,
        diabetes_label=diabetes,
        label_basis=basis,
        notes=payload.notes,
    )
    db.add(row)
    await db.flush()
    log.info(
        "research_case_recorded",
        case_id=str(row.id),
        domain=row.capture_domain,
        labels={
            "obesity": obesity.value,
            "hypertension": hypertension.value,
            "diabetes": diabetes.value,
        },
    )
    return _to_response(row)


def _to_response(row: ResearchTriageCase) -> ResearchCaseResponse:
    bmi = _bmi(row.height_cm, row.weight_kg)
    whtr = row.waist_cm / row.height_cm if row.height_cm else None
    return ResearchCaseResponse(
        id=row.id,
        capture_domain=row.capture_domain,
        age_years=row.age_years,
        sex=row.sex,
        height_cm=row.height_cm,
        weight_kg=row.weight_kg,
        waist_cm=row.waist_cm,
        bmi=round(bmi, 1),
        whtr=round(whtr, 3) if whtr is not None else None,
        systolic_bp_mmhg=row.systolic_bp_mmhg,
        diastolic_bp_mmhg=row.diastolic_bp_mmhg,
        hba1c_percent=row.hba1c_percent,
        fasting_glucose_mmol_l=row.fasting_glucose_mmol_l,
        obesity_label=row.obesity_label,
        hypertension_label=row.hypertension_label,
        diabetes_label=row.diabetes_label,
        label_basis=dict(row.label_basis or {}),
        study_subject_id=row.study_subject_id,
        created_at=row.created_at,
    )


async def list_research_cases(
    db: AsyncSession, *, limit: int = 100
) -> list[ResearchCaseResponse]:
    rows = (
        await db.scalars(
            select(ResearchTriageCase)
            .order_by(desc(ResearchTriageCase.created_at))
            .limit(limit)
        )
    ).all()
    return [_to_response(r) for r in rows]


_PRIORITY_RANK = {
    AcquisitionPriority.LOW: 0,
    AcquisitionPriority.MEDIUM: 1,
    AcquisitionPriority.HIGH: 2,
}


async def acquisition_worklist(
    db: AsyncSession,
    *,
    limit: int = 50,
    min_priority: AcquisitionPriority = AcquisitionPriority.LOW,
    scan: int = 500,
) -> list[AcquisitionWorklistItem]:
    """Rank participants by how much acquiring confirmatory ground truth would
    improve the model (active learning over the EDL uncertainty).

    Scans the most recent ``scan`` assessments, keeps one row per participant
    (their latest), scores each, drops those below ``min_priority``, and returns
    the top ``limit`` by acquisition value. Erased participants are excluded —
    they cannot be followed up.
    """
    stmt = (
        select(TriageAssessment, User.site_code)
        .join(User, User.id == TriageAssessment.user_id)
        .where(User.erased_at.is_(None))
        .order_by(desc(TriageAssessment.created_at))
        .limit(scan)
    )
    rows = (await db.execute(stmt)).all()

    seen: set[uuid.UUID] = set()
    items: list[AcquisitionWorklistItem] = []
    for assessment, site_code in rows:
        if assessment.user_id in seen:
            continue  # keep only the participant's most recent assessment
        seen.add(assessment.user_id)
        per_disease = [
            PerDiseaseRisk.model_validate(entry)
            for entry in (assessment.per_disease_risks or [])
        ]
        score = score_assessment(per_disease)
        if score is None or _PRIORITY_RANK[score.priority] < _PRIORITY_RANK[min_priority]:
            continue
        items.append(
            AcquisitionWorklistItem(
                assessment_id=assessment.id,
                user_id=assessment.user_id,
                site_code=site_code,
                driving_disease=score.driving_disease,
                confirmatory_test=score.confirmatory_test,
                acquisition_score=score.acquisition_score,
                epistemic_component=score.epistemic_component,
                boundary_component=score.boundary_component,
                priority=score.priority,
                rationale=score.rationale,
                created_at=assessment.created_at,
            )
        )

    items.sort(key=lambda i: i.acquisition_score, reverse=True)
    return items[:limit]


async def export_training_rows(db: AsyncSession) -> list[dict[str, object]]:
    """Emit the corpus as training rows: features + the three REAL per-disease
    labels + the capture domain. Consumed by the multi-head training pipeline
    (``--research-jsonl``) so Model 1 learns from recruited ground truth."""
    rows = (await db.scalars(select(ResearchTriageCase))).all()
    return [
        {
            "source": "research",
            "domain": r.capture_domain,
            "site": r.site_code,
            "age_years": r.age_years,
            "sex": r.sex,
            "height_cm": r.height_cm,
            "weight_kg": r.weight_kg,
            "waist_cm": r.waist_cm,
            "hip_cm": r.hip_cm,
            "systolic_bp_mmhg": r.systolic_bp_mmhg,
            "diastolic_bp_mmhg": r.diastolic_bp_mmhg,
            "obesity_label": r.obesity_label.value,
            "hypertension_label": r.hypertension_label.value,
            "diabetes_label": r.diabetes_label.value,
        }
        for r in rows
    ]


async def corpus_stats(db: AsyncSession) -> ResearchCorpusStats:
    rows = (await db.scalars(select(ResearchTriageCase))).all()

    def _dist(attr: str) -> dict[str, int]:
        counts = Counter(getattr(r, attr).value for r in rows)
        return {rc.value: counts.get(rc.value, 0) for rc in RiskClass}

    return ResearchCorpusStats(
        total=len(rows),
        by_domain=dict(Counter(r.capture_domain for r in rows)),
        by_site=dict(Counter(r.site_code for r in rows)),
        label_distribution=LabelDistribution(
            obesity=_dist("obesity_label"),
            hypertension=_dist("hypertension_label"),
            diabetes=_dist("diabetes_label"),
        ),
        with_bp=sum(1 for r in rows if r.systolic_bp_mmhg is not None),
        with_diabetes_marker=sum(
            1
            for r in rows
            if r.hba1c_percent is not None or r.fasting_glucose_mmol_l is not None
        ),
    )
