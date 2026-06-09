"""Anthropometric synthesis for datasets missing direct measurements.

Many of the public NCD datasets we harmonise (Pima diabetes, UCI heart disease,
stroke) lack one or more of the production inputs (``height_cm``, ``weight_kg``,
``waist_cm``). Rather than dropping those rows we synthesise the missing fields
from clinically-grounded priors so the model trains on a unified feature
schema. All synthesis is deterministic per ``(dataset_name, row_index)`` so
runs are reproducible.

Priors (population-level; chosen to reflect typical adult Sub-Saharan / global
NCD-cohort distributions):

* Height — sex- and age-conditional Gaussian (M: μ=175 σ=7 cm; F: μ=162 σ=6 cm),
  mild secular decline after 30.
* Weight — derived from BMI when available, else sex-conditional Gaussian
  (M: μ=75 σ=12 kg; F: μ=66 σ=11 kg) clipped to [40, 150].
* Waist — NHANES-style ``waist ≈ 30 + 2.2·BMI + 0.15·age + 8·(sex=M) + ε``
  with ``ε ~ N(0, 4)``, clipped to [50, 180].
* BP — when only one of systolic / diastolic is given, derive the other from
  the typical 40 mmHg pulse pressure with ``ε ~ N(0, 6)``.

The training meta.json records which fields were synthesised so the
calibration audit can stratify metrics by data provenance.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class SynthesisDecision:
    height_synthesised: bool
    weight_synthesised: bool
    waist_synthesised: bool
    systolic_synthesised: bool
    diastolic_synthesised: bool


def _seeded_rng(dataset: str, row_index: int) -> np.random.Generator:
    digest = hashlib.blake2b(
        f"{dataset}:{row_index}".encode(), digest_size=8
    ).digest()
    return np.random.default_rng(int.from_bytes(digest, "little"))


def synthesise_height_cm(
    rng: np.random.Generator, sex: str, age_years: int
) -> float:
    if sex == "MALE":
        mu, sigma = 175.0, 7.0
    elif sex == "FEMALE":
        mu, sigma = 162.0, 6.0
    else:
        mu, sigma = 168.5, 7.5
    decay = max(0.0, age_years - 30) * 0.05
    return float(np.clip(rng.normal(mu - decay, sigma), 140.0, 210.0))


def synthesise_weight_kg(
    rng: np.random.Generator,
    sex: str,
    height_cm: float,
    bmi: float | None,
) -> float:
    if bmi is not None and bmi > 0.0:
        return float(np.clip(bmi * (height_cm / 100.0) ** 2, 30.0, 250.0))
    mu, sigma = (75.0, 12.0) if sex == "MALE" else (66.0, 11.0)
    return float(np.clip(rng.normal(mu, sigma), 40.0, 150.0))


def synthesise_waist_cm(
    rng: np.random.Generator,
    sex: str,
    age_years: int,
    bmi: float,
) -> float:
    sex_offset = 8.0 if sex == "MALE" else 0.0
    base = 30.0 + 2.2 * bmi + 0.15 * age_years + sex_offset
    return float(np.clip(base + rng.normal(0.0, 4.0), 50.0, 180.0))


def synthesise_partner_bp(
    rng: np.random.Generator,
    known_value: float,
    known_is_systolic: bool,
) -> float:
    """Derive the missing half of a BP pair from a typical pulse pressure."""
    if known_is_systolic:
        return float(
            np.clip(0.55 * known_value + 12.0 + rng.normal(0.0, 6.0), 40.0, 140.0)
        )
    return float(
        np.clip(known_value + 40.0 + rng.normal(0.0, 6.0), 70.0, 250.0)
    )
