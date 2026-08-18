# Prospective Kiosk-Population Validation Plan

Purpose: close the improvement loop that the cross-sectional field study (the
*Victus Brief*) cannot, by measuring how the models perform **on the population
they are actually deployed to** — kiosk walk-ups — against facility-confirmed
ground truth. This is the study a reviewer will ask for before any clinical
claim; the field study trains the models, this study validates them in situ.

> This is a protocol, not code. It defines what to collect, how to link it, the
> endpoints, and the analysis. The schema additions it needs are small and noted
> in §5.

## 1. Why this is needed

- The field-study corpus is recruited from **facility attendees** (enriched
  prevalence, healthcare-seeking). The kiosk serves **community walk-ups**.
  Discrimination *and* calibration learned on the former will not transfer
  unchanged to the latter — they must be re-estimated, not assumed.
- The kiosk gathers **inference data without ground truth**. To validate (and
  eventually retrain), a subset of kiosk users must be followed to a
  facility-confirmed outcome and **linked back** to their kiosk capture.

## 2. Design

- **Type:** prospective diagnostic-accuracy study (STARD-aligned), kiosk index
  test vs facility reference standard.
- **Index tests:** (a) 3B-Triage GREEN/YELLOW/RED per disease; (b) TOI HR/RR.
- **Reference standards:**
  - Diabetes — HbA1c ≥ 6.5 % or FPG ≥ 7.0 mmol/L (the genuine proxy target).
  - Hypertension — standardized cuff BP ≥ 140/90 (rest 5 min, correct cuff).
  - Obesity — measured BMI ≥ 30 (deterministic; used to confirm the rule, not
    the model).
  - HR/RR — pulse oximeter / ECG and a 60-second manual respiratory count.
- **Recruitment:** consecutive consenting kiosk users at pilot sites who accept a
  **facility referral within 7 days**; target a pre-specified N per disease
  powered for the primary estimate (sensitivity at the operating threshold with
  a ±5–7 % CI) — to be set with the statistician, **not** assumed from the field
  study's N. Recruitment is additionally quota-managed across pigmentation
  bands (§3.4).
- **Primary outcomes:** per-disease sensitivity/specificity/PPV/NPV at the
  deployed threshold; ROC-AUC; **calibration (ECE + reliability curve)**;
  for TOI, **Bland-Altman bias + 95 % limits of agreement**, analysed against
  **pigmentation as a continuous covariate (§3.3)** and by ambient-light
  condition (the kiosk confound the controlled calibration study does not
  capture).
- **Subgroups (pre-specified):** pigmentation band (§3.4), sex, age band, site,
  urban/rural.

## 3. Skin-tone measurement

The equity claim this platform rests on — that performance does not degrade on
darker skin — can only be as good as the variable it is measured against.
Fitzpatrick is not that variable.

### 3.1 Why Fitzpatrick is retired as the analysis variable

- Fitzpatrick (1975) classifies **UV photosensitivity** — burn and tan response,
  for phototherapy dosing. It was never a pigmentation scale.
- Types I–IV originally described white skin; **V and VI were added later**. The
  scale therefore offers four gradations of light skin and two for everything
  darker — and Victus operates almost entirely inside the range it compresses.
- What attenuates rPPG is **melanin optical absorption**, strongest in the green
  wavelengths that CHROM and POS depend on most. Photosensitivity is a weak
  proxy for absorption, and weakest precisely where resolution is needed.
- Self-reported Fitzpatrick has poor reliability in people of colour, so the
  measurement error is largest in the stratum carrying the claim.

Fitzpatrick is **retained as a recorded secondary** for comparability with the
existing rPPG literature. It is no longer an analysis or model variable.

### 3.2 The three-layer scheme

| Layer | Instrument | Role |
| --- | --- | --- |
| **Primary analysis** | **ITA°** (Individual Typology Angle) from reflectance colourimetry | Continuous covariate; corrector-model feature |
| **Primary reporting** | **Monk Skin Tone (MST), 10-point** | Recruitment quotas, subgroup tables, participant-facing description |
| **Secondary** | Fitzpatrick I–VI | Literature comparability only |

ITA° is derived from CIELAB as `ITA = arctan((L* − 50) / b*) × 180/π`. It is
continuous, instrument-measured, and observer-independent — which is what makes
the primary analysis in §3.3 possible. MST carries the reporting because its
ten points give real granularity at the dark end, where Fitzpatrick gives two.

### 3.3 Measurement protocol

- **Site: the forehead ROI** — the skin actually being measured by the camera.
  This is a deliberate departure from the dermatological convention of reading
  constitutive pigment at the inner upper arm: for rPPG, the *facultative*
  pigment at the measurement site is what attenuates the signal. Record an
  inner-arm reading as a secondary where feasible, to separate constitutive from
  sun-exposed pigment.
- **Instrument:** reflectance colourimeter / spectrophotometer reporting CIELAB,
  white-standard calibrated before each session; reading recorded on the
  calibration record, not the subject, because facultative pigment varies over
  time.
- **Assignment:** ITA and MST assigned by a trained collector under specified
  ambient lighting. Self-reported MST is acceptable in the *field product* but
  **not** in the validation rail — observer or self-assignment under
  uncontrolled kiosk lighting is not a defensible study measurement.
- **Timing:** taken at study-session registration, before capture, and locked
  with the session (§ existing session-lock behaviour).

### 3.4 Analysis and banding

**Primary analysis is continuous, not categorical.** Regress absolute error
(and, separately, recovered SNR) on ITA° across the cohort and test the slope
against a pre-specified margin. A dose–response result — *"agreement does not
degrade with pigmentation; slope CI excludes a clinically material effect"* — is
both stronger evidence and materially cheaper to power than pairwise category
comparison.

**Banding is secondary and pre-specified.** Two constraints shape it:

- Ten MST strata is not fundable. Limits of agreement need roughly **30–50 pairs
  per stratum** for a usable confidence interval; ten strata implies 300–500
  subjects for the TOI endpoint alone.
- The **conventional ITA dermatology cut-points also compress the dark end**
  (`brown` −30° to 10°, `dark` < −30°). Adopting them uncritically would
  reproduce the Fitzpatrick failure in a new coordinate system.

Therefore: **collapse the light end, resolve the dark end, and define the dark
bands by cohort quantile rather than by the conventional cut-points.** Indicative
shape, to be fixed with the statistician before enrolment opens:

| Band | Composition | Intent |
| --- | --- | --- |
| A | MST 1–4 (ITA above the `intermediate` boundary) | Collapsed — sparse in target population |
| B | MST 5–6 | |
| C | MST 7–8 | Resolved — the range Fitzpatrick V–VI conflates |
| D | MST 9–10 | Resolved — the darkest tertile by cohort quantile |

**Equivalence framing.** The subgroup claim is stated as a pre-specified
equivalence test — the difference in MAE between the darkest and lightest
enrolled bands must fall within a margin **justified clinically, not chosen for
convenience** — and powered accordingly. Descriptive per-stratum tables do not
support a fairness claim; an equivalence test does.

**Reporting.** Publish the achieved enrolment distribution across MST. Recruiting
the range is the evidence; claiming it is not.

## 4. Consent & governance

Distinct from the anonymous kiosk wellness flow: this requires **explicit
research consent** (HREC/NHREC, POPIA/NDPA per [[feedback-zimbabwe-legislation]]
jurisdiction), because the kiosk capture is deliberately linked to identified
facility results. Reuse the existing study pre-registration + erasure machinery;
linkage identifiers live only in the consented research record and are erasable.

**Skin tone is a distinct data-protection question.** An instrument-measured
pigmentation value is not equivalent to the optional self-reported
`race_ethnicity` field already covered in `ENROLLMENT_DPIA.md`: it may reveal
racial or ethnic origin and therefore engage special-category provisions under
POPIA, the NDPA and the ZW Cyber & Data Protection Act. Before enrolment,
`ENROLLMENT_DPIA.md` must be revised to cover ITA/MST collection — lawful basis,
necessity argument (it is necessary: the fairness claim cannot be evidenced
without it), retention, and erasure behaviour.

## 5. Schema additions (small, deferred build)

Deliberately **not** built yet — the study/ethics design must lead the schema.
The additions are additive; no existing column is dropped.

**Linkage.** A kiosk session already anchors a pseudonymous `users` row at
consent. To link a kiosk capture to its later facility-confirmed
`research_triage_cases` row:

1. At kiosk completion, if the participant opts into the validation study, mint a
   short **validation linkage code** and show/send it with their result.
2. At the facility, the data collector enters that code alongside the confirmed
   labels (a new optional `validation_code` column on `research_triage_cases`,
   plus the kiosk `users.id` / `toi_assessments.id` it resolves to).
3. The analysis joins kiosk index predictions ↔ facility reference rows on the
   code.

**Skin tone.** Two additive columns, placed to match how each value behaves:

| Column | Table | Why there |
| --- | --- | --- |
| `monk_skin_tone` (1–10, nullable) | `study_subjects` | Stable descriptor of the person |
| `ita_forehead_degrees` (float, nullable) | `rppg_calibration_records` | Measured per capture; facultative pigment varies over time |

`skin_tone_estimate` (Fitzpatrick) is retained on both `toi_assessments` and
`rppg_calibration_records` as the recorded secondary.

**Corrector-model consequence.** `toi_corrector_v1` currently takes
`fitzpatrick_ordinal` as a trained input feature. Replacing it with continuous
`ita_forehead_degrees` is strictly more information and removes arbitrary
binning, but **requires retraining the corrector**. The model is small; this is
cheap now and expensive after data collection begins under the old feature.

**Downstream:** `calibration/statistics.py` currently stratifies via
`by_fitzpatrick`; this becomes a continuous regression plus banded secondary.
Contracts, the three calibration/study web forms, `MODEL_DATA_ARCHITECTURE.md`
and the public marketing copy (which states a Fitzpatrick III–VI claim) all
follow.

## 6. Analysis & retraining

- Compute §2 metrics overall and per subgroup on the **linked prospective set**
  using `training/evaluation.py` (ROC-AUC, ECE, reliability, Bland-Altman) with
  `group_holdout_split` for site/country generalisation.
- Run the §3.4 continuous pigmentation analysis as a pre-specified primary, with
  banded subgroup tables as secondary.
- Emit an updated **model card** (`training/model_card.py`) recording the
  prospective metrics, the populations validated, and **the achieved MST
  enrolment distribution**.
- **Recalibrate** (e.g., temperature scaling / per-site intercepts) on the
  prospective set before any threshold change; only then consider folding the
  newly-labelled, linked kiosk captures into the training corpus — which is the
  point at which "the kiosk improves the model" becomes literally true.

## 7. Exit criteria

A disease's kiosk claim is supportable only when, on the prospective set:

- pre-specified sensitivity is met with its CI;
- calibration error is within the agreed bound;
- **the pigmentation slope (§3.4) excludes a clinically material effect**, and
  the darkest-vs-lightest band equivalence test passes its pre-specified margin;
- the achieved enrolment distribution demonstrates the dark bands were actually
  recruited, not merely defined.

Until then the surface stays **screening, not diagnosis**.
