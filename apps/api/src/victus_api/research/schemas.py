"""Research-console DTOs: labelled triage-case capture + corpus statistics."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from victus_api.db.models import RiskClass
from victus_api.triage.acquisition import AcquisitionPriority
from victus_api.triage.schemas import Disease, Sex


class CaptureDomain(str, enum.Enum):
    """Measurement provenance — feeds the DANN domain head at training time."""

    CLINICAL_GRADE = "CLINICAL_GRADE"
    CHW_TAPE_MEASURE = "CHW_TAPE_MEASURE"


class ResearchCaseCreate(BaseModel):
    """A labelled case. Obesity/hypertension labels are derived from the measured
    BMI/BP; diabetes from HbA1c or fasting glucose. Any label may be overridden
    by a clinician. Hypertension needs a BP reading (or override); diabetes needs
    a glucose marker (or override) — otherwise the label is refused, not guessed.
    """

    model_config = ConfigDict(extra="forbid")

    age_years: Annotated[int, Field(ge=1, le=120)]
    sex: Sex
    height_cm: Annotated[float, Field(ge=50, le=250)]
    weight_kg: Annotated[float, Field(ge=5, le=400)]
    waist_cm: Annotated[float, Field(ge=30, le=250)]
    hip_cm: Annotated[float, Field(ge=40, le=250)] | None = None
    systolic_bp_mmhg: Annotated[float, Field(ge=50, le=300)] | None = None
    diastolic_bp_mmhg: Annotated[float, Field(ge=30, le=200)] | None = None
    safety_triggers: list[str] = Field(default_factory=list, max_length=20)
    contextual: list[str] = Field(default_factory=list, max_length=20)
    # Diabetes ground truth — supply at least one (or a diabetes_label override).
    fasting_glucose_mmol_l: Annotated[float, Field(ge=1.0, le=50.0)] | None = None
    hba1c_percent: Annotated[float, Field(ge=3.0, le=20.0)] | None = None
    capture_domain: CaptureDomain = CaptureDomain.CLINICAL_GRADE
    study_subject_id: uuid.UUID | None = None
    # Optional clinician overrides for the auto-derived labels.
    obesity_label: RiskClass | None = None
    hypertension_label: RiskClass | None = None
    diabetes_label: RiskClass | None = None
    notes: Annotated[str, Field(max_length=2000)] | None = None

    @model_validator(mode="after")
    def _bp_pair(self) -> ResearchCaseCreate:
        if (self.systolic_bp_mmhg is None) != (self.diastolic_bp_mmhg is None):
            raise ValueError("Provide both systolic and diastolic BP, or neither.")
        return self


class ResearchCaseResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    capture_domain: str
    age_years: int
    sex: str
    height_cm: float
    weight_kg: float
    waist_cm: float
    bmi: float
    whtr: float | None
    systolic_bp_mmhg: float | None
    diastolic_bp_mmhg: float | None
    hba1c_percent: float | None
    fasting_glucose_mmol_l: float | None
    obesity_label: RiskClass
    hypertension_label: RiskClass
    diabetes_label: RiskClass
    label_basis: dict[str, str]
    study_subject_id: uuid.UUID | None
    created_at: datetime


class LabelDistribution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    obesity: dict[str, int]
    hypertension: dict[str, int]
    diabetes: dict[str, int]


class ResearchImportError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    row: int  # zero-based index in the submitted batch
    error: str


class ResearchImportSummary(BaseModel):
    """Outcome of a REDCap/ODK/CSV import — per-row successes and failures."""

    model_config = ConfigDict(extra="forbid")

    imported: int
    failed: int
    errors: list[ResearchImportError]


class ResearchCorpusStats(BaseModel):
    """Funder-facing snapshot of the labelled triage corpus."""

    model_config = ConfigDict(extra="forbid")

    total: int
    by_domain: dict[str, int]
    by_site: dict[str, int]
    label_distribution: LabelDistribution
    with_bp: int
    with_diabetes_marker: int


class AcquisitionWorklistItem(BaseModel):
    """One participant on the confirmatory-testing worklist, ranked by how much
    acquiring their ground truth would improve the model (uncertainty × decision
    boundary from the EDL output). One row per participant (latest assessment)."""

    model_config = ConfigDict(extra="forbid")

    assessment_id: uuid.UUID
    user_id: uuid.UUID
    site_code: str
    driving_disease: Disease
    confirmatory_test: str
    acquisition_score: float
    epistemic_component: float
    boundary_component: float
    priority: AcquisitionPriority
    rationale: str
    created_at: datetime
