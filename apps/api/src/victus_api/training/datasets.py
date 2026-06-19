"""Per-source loaders that emit :class:`HarmonizedRecord` lists.

Each loader is defensive about missing files (returns an empty list with a
warning log), tolerates the common UCI sentinel ``?`` for missing values, and
records provenance via the ``source`` and ``domain`` fields so downstream
calibration metrics can stratify by dataset and the DANN adversary has a
target to predict.
"""

from __future__ import annotations

import csv
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

from victus_api.core.logging import get_logger
from victus_api.training.harmonize import (
    Domain,
    HarmonizedRecord,
    bodyfat_risk_class,
    diabetes_risk_class,
    heart_risk_class,
    stroke_risk_class,
)
from victus_api.training.synthesis import (
    _seeded_rng,
    synthesise_height_cm,
    synthesise_partner_bp,
    synthesise_waist_cm,
    synthesise_weight_kg,
)
from victus_api.triage.schemas import RiskClass

log = get_logger(__name__)


# --- Body fat (true H/W/waist, units: lb / in / cm) --------------------------


def load_bodyfat(path: Path) -> list[HarmonizedRecord]:
    if not path.is_file():
        log.warning("bodyfat_csv_missing", path=str(path))
        return []

    df = pd.read_csv(path)
    records: list[HarmonizedRecord] = []
    for _idx, row in df.iterrows():
        body_fat = float(row["BodyFat"])
        weight_kg = float(row["Weight"]) * 0.45359237  # lb → kg
        height_cm = float(row["Height"]) * 2.54  # in → cm
        waist_cm = float(row["Abdomen"])  # already in cm
        hip_cm = float(row["Hip"]) if pd.notna(row.get("Hip")) else None
        age = int(row["Age"])
        if height_cm < 100.0 or weight_kg < 30.0:
            continue
        records.append(
            HarmonizedRecord(
                source="bodyfat",
                domain=Domain.CLINICAL_GRADE,
                height_cm=round(height_cm, 1),
                weight_kg=round(weight_kg, 1),
                waist_cm=round(waist_cm, 1),
                hip_cm=round(hip_cm, 1) if hip_cm else None,
                age_years=age,
                sex="MALE",  # cohort is all male
                systolic_bp_mmhg=None,
                diastolic_bp_mmhg=None,
                risk_class=bodyfat_risk_class(body_fat),
            )
        )
    log.info("bodyfat_loaded", count=len(records))
    return records


# --- Pima diabetes -----------------------------------------------------------


def load_diabetes(path: Path) -> list[HarmonizedRecord]:
    if not path.is_file():
        log.warning("diabetes_csv_missing", path=str(path))
        return []

    df = pd.read_csv(path)
    records: list[HarmonizedRecord] = []
    for idx, row in df.iterrows():
        bmi = float(row["BMI"])
        glucose = float(row["Glucose"])
        diastolic = float(row["BloodPressure"])
        age = int(row["Age"])
        outcome = int(row["Outcome"])
        if bmi <= 0.0 or age <= 0:
            continue

        rng = _seeded_rng("diabetes", int(idx))
        height_cm = synthesise_height_cm(rng, "FEMALE", age)
        weight_kg = synthesise_weight_kg(rng, "FEMALE", height_cm, bmi=bmi)
        waist_cm = synthesise_waist_cm(rng, "FEMALE", age, bmi)
        systolic = (
            synthesise_partner_bp(rng, diastolic, known_is_systolic=False)
            if diastolic > 0.0
            else None
        )
        diastolic_val = diastolic if diastolic > 0.0 else None

        records.append(
            HarmonizedRecord(
                source="diabetes",
                domain=Domain.SYNTHETIC,
                height_cm=round(height_cm, 1),
                weight_kg=round(weight_kg, 1),
                waist_cm=round(waist_cm, 1),
                hip_cm=None,
                age_years=age,
                sex="FEMALE",
                systolic_bp_mmhg=round(systolic, 1) if systolic is not None else None,
                diastolic_bp_mmhg=round(diastolic_val, 1)
                if diastolic_val is not None
                else None,
                risk_class=diabetes_risk_class(outcome, glucose, bmi),
            )
        )
    log.info("diabetes_loaded", count=len(records))
    return records


# --- UCI heart disease (Cleveland / Hungarian / Switzerland / VA) ------------


_HEART_COLS: tuple[str, ...] = (
    "age",
    "sex",
    "cp",
    "trestbps",
    "chol",
    "fbs",
    "restecg",
    "thalach",
    "exang",
    "oldpeak",
    "slope",
    "ca",
    "thal",
    "target",
)


def _heart_iter(path: Path) -> Iterator[dict[str, str]]:
    with path.open("r", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        for row in reader:
            if len(row) < len(_HEART_COLS):
                continue
            yield dict(zip(_HEART_COLS, row, strict=False))


def _heart_float(raw: str) -> float | None:
    cleaned = raw.strip()
    if cleaned in ("", "?", "-9", "-9.0"):
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def load_heart_disease(dir_path: Path) -> list[HarmonizedRecord]:
    records: list[HarmonizedRecord] = []
    files = [
        "processed.cleveland.data",
        "processed.hungarian.data",
        "processed.switzerland.data",
        "processed.va.data",
    ]
    row_idx = 0
    for fname in files:
        path = dir_path / fname
        if not path.is_file():
            log.warning("heart_csv_missing", path=str(path))
            continue
        for parsed in _heart_iter(path):
            age_f = _heart_float(parsed["age"])
            sex_f = _heart_float(parsed["sex"])
            target_f = _heart_float(parsed["target"])
            if age_f is None or sex_f is None or target_f is None:
                continue
            age = int(age_f)
            if age <= 0:
                continue
            sex = "MALE" if int(sex_f) == 1 else "FEMALE"
            trestbps = _heart_float(parsed["trestbps"])
            chol = _heart_float(parsed["chol"])
            fbs_v = _heart_float(parsed["fbs"])
            fbs = int(fbs_v) if fbs_v is not None else None
            target = int(target_f)

            rng = _seeded_rng("heart", row_idx)
            row_idx += 1
            height_cm = synthesise_height_cm(rng, sex, age)
            weight_kg = synthesise_weight_kg(rng, sex, height_cm, bmi=None)
            bmi = weight_kg / ((height_cm / 100.0) ** 2)
            waist_cm = synthesise_waist_cm(rng, sex, age, bmi)

            if trestbps is not None and 50.0 <= trestbps <= 260.0:
                systolic: float | None = trestbps
                diastolic: float | None = synthesise_partner_bp(
                    rng, trestbps, known_is_systolic=True
                )
            else:
                systolic = None
                diastolic = None

            records.append(
                HarmonizedRecord(
                    source="heart",
                    domain=Domain.CLINICAL_GRADE,
                    height_cm=round(height_cm, 1),
                    weight_kg=round(weight_kg, 1),
                    waist_cm=round(waist_cm, 1),
                    hip_cm=None,
                    age_years=age,
                    sex=sex,
                    systolic_bp_mmhg=round(systolic, 1) if systolic is not None else None,
                    diastolic_bp_mmhg=round(diastolic, 1) if diastolic is not None else None,
                    risk_class=heart_risk_class(
                        target, trestbps=trestbps, chol=chol, fbs=fbs
                    ),
                )
            )
    log.info("heart_loaded", count=len(records))
    return records


# --- Stroke ------------------------------------------------------------------


def load_stroke(path: Path) -> list[HarmonizedRecord]:
    if not path.is_file():
        log.warning("stroke_csv_missing", path=str(path))
        return []
    df = pd.read_csv(path)
    records: list[HarmonizedRecord] = []
    for idx, row in df.iterrows():
        gender = str(row["gender"]).upper()
        if gender not in ("MALE", "FEMALE"):
            continue
        age_v = float(row["age"])
        if age_v < 13.0:  # paediatric data — skip, our target is adult NCD
            continue
        age = round(age_v)
        bmi_raw = row.get("bmi")
        bmi = float(bmi_raw) if pd.notna(bmi_raw) else None
        if bmi is None or bmi <= 0.0:
            continue

        hypertension = int(row["hypertension"]) if pd.notna(row["hypertension"]) else 0
        heart_disease = int(row["heart_disease"]) if pd.notna(row["heart_disease"]) else 0
        stroke = int(row["stroke"]) if pd.notna(row["stroke"]) else 0

        rng = _seeded_rng("stroke", int(idx))
        height_cm = synthesise_height_cm(rng, gender, age)
        weight_kg = synthesise_weight_kg(rng, gender, height_cm, bmi=bmi)
        waist_cm = synthesise_waist_cm(rng, gender, age, bmi)

        records.append(
            HarmonizedRecord(
                source="stroke",
                domain=Domain.SYNTHETIC,
                height_cm=round(height_cm, 1),
                weight_kg=round(weight_kg, 1),
                waist_cm=round(waist_cm, 1),
                hip_cm=None,
                age_years=age,
                sex=gender,
                systolic_bp_mmhg=None,
                diastolic_bp_mmhg=None,
                risk_class=stroke_risk_class(stroke, hypertension, heart_disease, bmi),
            )
        )
    log.info("stroke_loaded", count=len(records))
    return records


# --- Orchestrator ------------------------------------------------------------


def load_research_jsonl(path: Path) -> list[dict]:
    """Load the research-console export (``/research/triage-cases/export``).

    Each line is a recruited, ground-truth-labelled case: features + the three
    REAL per-disease labels + capture domain. These labels are used directly
    (not re-derived from features), so the model learns from clinician-confirmed
    ground truth — the whole point of the recruitment data.
    """
    import json

    if not path.is_file():
        log.warning("research_jsonl_missing", path=str(path))
        return []
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    log.info("research_jsonl_loaded", count=len(rows), path=str(path))
    return rows


def load_all(data_dir: Path) -> list[HarmonizedRecord]:
    all_records: list[HarmonizedRecord] = []
    all_records.extend(load_bodyfat(data_dir / "body_fat_prediction" / "bodyfat.csv"))
    all_records.extend(load_diabetes(data_dir / "diabetes" / "diabetes.csv"))
    all_records.extend(load_heart_disease(data_dir / "heart_disease_ml"))
    all_records.extend(load_stroke(data_dir / "healthcare-dataset-stroke-data.csv"))
    return all_records


def class_distribution(records: list[HarmonizedRecord]) -> dict[RiskClass, int]:
    out: dict[RiskClass, int] = {}
    for r in records:
        out[r.risk_class] = out.get(r.risk_class, 0) + 1
    return out


def source_distribution(records: list[HarmonizedRecord]) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in records:
        out[r.source] = out.get(r.source, 0) + 1
    return out


def domain_distribution(records: list[HarmonizedRecord]) -> dict[Domain, int]:
    out: dict[Domain, int] = {}
    for r in records:
        out[r.domain] = out.get(r.domain, 0) + 1
    return out


# ---------------------------------------------------------------------------
# CHW_TAPE_MEASURE: noise-injected copies of CLINICAL_GRADE records
# ---------------------------------------------------------------------------


def _inject_chw_noise(
    record: HarmonizedRecord, rng: np.random.Generator
) -> HarmonizedRecord:
    """Realistic field-collection noise model for community health workers.

    Empirical measurement-error distributions for tape measure / digital scale /
    aneroid cuff in field conditions:

    * Height: ±0.5 cm Gaussian + 1 cm quantization (subject barefoot,
      hard floor not guaranteed).
    * Weight: ±0.3 kg Gaussian + 0.5 kg quantization (clothing variability).
    * Waist: ±2.0 cm Gaussian + 1 cm quantization (single largest source
      of inter-observer variance in NCD field studies).
    * Hip: ±2.0 cm Gaussian + 1 cm quantization.
    * BP (when present): ±4 mmHg Gaussian + 2 mmHg quantization (aneroid
      cuff + auscultation by CHW vs digital cuff baseline).

    The underlying biology — and therefore ``risk_class`` — is unchanged.
    The DANN adversary's job is to learn that this noise should not affect
    risk-class predictions.
    """

    def _q(value: float, sigma: float, q_step: float, lo: float, hi: float) -> float:
        noisy = value + rng.normal(0.0, sigma)
        quantized = round(noisy / q_step) * q_step
        return float(np.clip(quantized, lo, hi))

    new_height = _q(record.height_cm, 0.5, 1.0, 50.0, 250.0)
    new_weight = _q(record.weight_kg, 0.3, 0.5, 5.0, 400.0)
    new_waist = _q(record.waist_cm, 2.0, 1.0, 30.0, 250.0)
    new_hip = _q(record.hip_cm, 2.0, 1.0, 40.0, 250.0) if record.hip_cm else None
    new_systolic = (
        _q(record.systolic_bp_mmhg, 4.0, 2.0, 50.0, 260.0)
        if record.systolic_bp_mmhg is not None
        else None
    )
    new_diastolic = (
        _q(record.diastolic_bp_mmhg, 4.0, 2.0, 30.0, 160.0)
        if record.diastolic_bp_mmhg is not None
        else None
    )

    return replace(
        record,
        source=f"{record.source}_chw_noisy",
        domain=Domain.CHW_TAPE_MEASURE,
        height_cm=round(new_height, 1),
        weight_kg=round(new_weight, 1),
        waist_cm=round(new_waist, 1),
        hip_cm=round(new_hip, 1) if new_hip is not None else None,
        systolic_bp_mmhg=round(new_systolic, 1) if new_systolic is not None else None,
        diastolic_bp_mmhg=round(new_diastolic, 1)
        if new_diastolic is not None
        else None,
    )


def synthesize_chw_domain(
    records: list[HarmonizedRecord],
    *,
    k_multiplier: int = 4,
    seed: int = 17,
) -> list[HarmonizedRecord]:
    """Generate the CHW_TAPE_MEASURE domain by noise-injecting clinical-grade rows.

    For each source CLINICAL_GRADE record we emit ``k_multiplier`` independent
    noise realisations, giving the DANN adversary enough mass in the CHW
    domain to be a non-trivial classifier. Sampling is deterministic per
    ``(source_row_idx, replicate_idx)``.
    """
    parents = [r for r in records if r.domain == Domain.CLINICAL_GRADE]
    out: list[HarmonizedRecord] = []
    for parent_idx, parent in enumerate(parents):
        for k in range(k_multiplier):
            rng = _seeded_rng(f"chw:{seed}:{parent.source}:{parent_idx}", k)
            out.append(_inject_chw_noise(parent, rng))
    log.info(
        "chw_domain_synthesized",
        parents=len(parents),
        replicates_per_parent=k_multiplier,
        total=len(out),
    )
    return out
