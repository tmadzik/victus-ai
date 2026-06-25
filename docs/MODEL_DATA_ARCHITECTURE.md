# Victus AI — Model & Data Architecture, and Pre-Review Assessment

Audience: the bioinformatics reviewer. Purpose: (1) confirm how the end-user
Mobile Clinic Gateway relates to the model-training architecture, (2) map the
*Victus Brief* (NCD Research Proposal) onto the 3B-Triage training corpus,
(3) describe the TOI training/calibration model and concurrency, and (4) state
honestly where this will draw push-back in expert review.

> TL;DR — The data-*gathering-for-training* mechanism for 3B-Triage already
> exists and already encodes the Brief's diagnostic thresholds. **No new ML model
> is needed for data gathering.** The Brief is a *field-study protocol*, not a
> document to be "ingested" by a model. The real work to survive review is in the
> ML *methodology* layer (task definition, validation, generalisation, claims),
> not the collection layer.

---

## 1. What we have actually built, and the "improvement loop"

There are **two distinct surfaces**, and conflating them is the main risk to the
"the platform improves what the kiosk gathers" claim:

| Surface | Role | Produces |
|---|---|---|
| **Mobile Clinic Gateway (kiosk + WhatsApp)** | End-user **inference + delivery** front-end | rPPG-derived vitals (`toi_assessments`), capture quality metadata, triage *predictions* — **no ground-truth labels, no reference-device pairs** |
| **Research console** (`/research`, `research_triage_cases`) and **Calibration console** (`rppg_calibration_records`, study pre-registration) | **Training-data gathering** front-ends | Clinically-confirmed labelled triage cases; reference-vs-rPPG calibration pairs |

The training pipeline (`victus_api/training/*`) consumes the **console** corpora,
produces the models, and the kiosk then *calls those models*. So:

- ✅ **True:** as the models improve (from the research + calibration corpora),
  the kiosk's output quality improves — the kiosk runs the same `assess_toi`
  pipeline and (for triage) the same EDL model.
- ⚠️ **Not true (by design):** the kiosk does **not** feed the training loop. An
  anonymous walk-up capture has no HbA1c, no cuff BP, no reference oximeter — so
  it cannot become a labelled training row or a calibration pair. **Data without
  ground truth is not training data.**

**Conclusion for the reviewer:** the "former improves the latter" relationship is
real, but the *latter that gathers training data* is the research/calibration
study (the Brief), **not** the kiosk. If the intent is for the kiosk's own
captures to continuously retrain the models, that is **not** what exists and would
require a ground-truth linkage step (a kiosk participant who later gets bloods/BP
at a facility, linked back) or human-in-the-loop labelling — see §5.

---

## 2. The Victus Brief → 3B-Triage: do we need "one more model"?

**No.** The Brief ("NCD Research Proposal — SA/Nigeria Hybrid Model") is a
**field data-collection protocol**: 5,000 participants/country, anthropometry +
≥2 BP readings + fasting glucose/HbA1c, with primary outcomes

- Obesity: BMI ≥ 30 kg/m²
- Hypertension: BP ≥ 140/90 mmHg or on treatment
- Diabetes: HbA1c ≥ 6.5 % or FPG ≥ 7.0 mmol/L or on treatment

These map **1:1** onto what the platform already implements:

- **Schema** `research_triage_cases` already stores exactly the Brief's Minimum
  Dataset (age, sex, height, weight, waist, hip, systolic/diastolic BP, FPG,
  HbA1c, behavioural symptoms, `site_code`, `capture_domain`) plus the three
  per-disease labels and a `label_basis` audit string.
- **Labelling** `research/service.py` already auto-derives the labels from the
  Brief's thresholds (`_derive_obesity` BMI bands, `_derive_hypertension`
  140/90 & 130/80 & 180/110, `_derive_diabetes` HbA1c 6.5/5.7/9.0 + FPG 7.0 —
  ADA/WHO cut-points), clinician-overridable, with the basis recorded.
- **Training** `ResearchTriageCase` is documented as the export corpus for the
  multi-head DANN-EDL (Model 1), with `capture_domain` feeding the domain head.

So the Brief is consumed by **people running the study → the research console →
the training corpus**, not by a model reading a PDF. The only thing genuinely
*missing* is a **data-ingestion bridge**, not a model:

> **Recommended addition (pipeline, not ML):** the Brief specifies REDCap/ODK
> field capture. Add an import path (REDCap/ODK/CSV → `research_triage_cases`)
> so the field study's export lands in the training corpus without manual
> re-entry. This is the one concrete build item implied by the Brief.

---

## 3. TOI training/calibration model, and concurrency

**Model 2 (TOI)** is not a single end-to-end network; it is a signal pipeline
(CHROM/POS chrominance rPPG) plus a **calibration corrector**
(`training/toi_corrector.py`) fit on `rppg_calibration_records` — paired
*reference device* (oximeter / cuff / ECG) vs *rPPG* captures, with study
pre-registration and Bland-Altman tooling already present.

- **Concurrency:** Model 1 (tabular EDL) and Model 2 (signal corrector) are
  **independent** — different data, different pipelines — so they train and serve
  concurrently with no contention. That is fine operationally.
- **Caveat:** "concurrent" here means *parallel and independent*, **not
  integrated**. There is no multimodal fusion of anthropometry + vitals into one
  per-person score. If that is the goal, it is a *future* fusion model needing
  **linked, labelled** per-participant data (the kiosk could supply the linkage —
  it gathers both face vitals and, via WhatsApp, the intake — but still without
  ground-truth labels).

**Sufficiency:** the calibration *mechanism* is sufficient and well-conceived for
**HR/RR**. It is **not** sufficient to substantiate the BP / CVD-risk /
stroke-risk / BMI biomarkers — see §4.

---

## 4. Where this will fail / draw push-back in expert review

The collection layer (the Brief) is strong — SOPs, QA, ethics (HREC/POPIA/NDPA),
measurement protocols. The exposure is in the **ML methodology and the claims**.

### 4.1 3B-Triage
1. **Label leakage / circularity (the big one).** Obesity (BMI≥30) and
   hypertension (BP≥140/90) labels are *deterministic functions of measured
   inputs*. If BMI/BP are also model inputs, the model "predicts" the label from
   the measurement that defines it — the ML adds nothing over a threshold rule.
   The genuine predictive task is **diabetes from non-invasive anthropometry +
   symptoms** (predicting HbA1c-confirmed status *without* the blood test). The
   task definition must state, per target, exactly which inputs are allowed, and
   the proxy task must **exclude the defining measurement**.
2. **Detection vs prediction.** The Brief is **cross-sectional** → it supports
   *classification of prevalent disease*, not *prediction of future risk*. Claims
   of "early detection" / "risk prediction" will be challenged; the wording must
   match the design (prevalent-case detection).
3. **Train/deploy population mismatch.** The study samples **facility attendees**
   ("attending facility that day") — a healthcare-seeking, enriched-prevalence
   population. The kiosk serves **walk-up community** users. Calibration and
   prevalence will not transfer. Needs site-held-out and country-held-out
   validation, ideally prospective kiosk-population validation.
4. **Power for subgroups.** ~5,000/country with diabetes prevalence ≈5–10 % gives
   only a few hundred positives; stratifying by disease × domain × site ×
   Fitzpatrick × sex thins this quickly. Subgroup calibration power is doubtful.
5. **DANN domain-invariance** (CLINICAL_GRADE / CHW_TAPE_MEASURE / SYNTHETIC)
   needs adequate N per domain and evidence it *improves CHW-measure
   generalisation on a held-out CHW set* — not just lowers training loss; and that
   invariance to synthetic artefacts doesn't wash out real signal.
6. **EDL/Dirichlet uncertainty** claims (epistemic vs aleatoric, OOD abstention)
   need calibration evidence: ECE, reliability diagrams, coverage/accuracy
   trade-off curves with thresholds set on validation data.

### 4.2 TOI (rPPG)
1. **HR / RR:** defensible. Validate with **Bland-Altman vs oximeter/ECG —
   report limits of agreement, not just r/MAE — stratified by Fitzpatrick**.
2. **BP from a single camera:** scientifically contested (no pulse-transit-time
   from one sensor). Will be flagged as overclaiming; would need AAMI/ESH/ISO
   81060-2-grade validation, and even then rPPG-BP is not accepted practice.
3. **"Stress index", "CVD risk", "stroke risk", "BMI" from face video:** no rPPG
   ground truth exists for these. Marking them `experimental` in code is good, but
   the **product framing must not present them as measurements** — reframe as
   exploratory/research-only or remove.
4. **HRV:** RMSSD/beat-to-beat is sensitive to frame-rate jitter and a 30 s window
   is short; validate against ECG R-R.
5. **Calibration generalisation:** a corrector fit on one device/lighting/camera
   overfits; needs cross-device, cross-site, controlled-vs-uncontrolled-light
   validation. Correcting toward a reference cannot manufacture a signal that
   isn't physically present (e.g., BP). The kiosk's **uncontrolled lighting** is a
   confound the controlled calibration study won't capture → another train/deploy
   gap.

### 4.3 Data / MLOps / regulatory (cross-cutting)
- No documented **train/val/test protocol**, dataset/model **versioning &
  lineage**, **drift monitoring**, **model cards**, or **pre-registered ML
  analysis plan** (the calibration study *is* pre-registered — extend that ethos
  to Model 1).
- **Regulatory:** risk states + "risk prediction" likely cross into **Software as
  a Medical Device** (SAHPRA / NAFDAC). The "wellness, not diagnosis" framing
  helps but the *claims must match the evidence*. The Brief covers research
  ethics well; the **product** regulatory pathway is unaddressed.

---

## 5. Recommended minimal additions — status

All five are addressed in this change set (the prospective study is a protocol,
the rest are code):

1. ✅ **Predictive tasks defined + leakage guard** — `triage/tasks.py` declares,
   per disease, the task kind and the forbidden (label-defining) features, with a
   `mask_vector` the training/inference paths apply so a head never sees its own
   defining measurement. Unit-tested.
2. ✅ **Field-study import bridge** — `research/importer.py` +
   `POST /research/triage-cases/import` (REDCap/ODK/CSV → `research_triage_cases`,
   alias-tolerant, per-row error reporting, reuses label auto-derivation).
3. ✅ **Validation/calibration harness + model cards** — `training/evaluation.py`
   (ROC-AUC, Brier, ECE, reliability, Bland-Altman LoA, group-held-out split) and
   `training/model_card.py`. Pure-function metrics unit-tested.
4. ✅ **TOI biomarkers gated** — HRV + stress flagged `experimental` and withheld
   by default (`TOI_EXPOSE_EXPERIMENTAL_BIOMARKERS`); README corrected (BP/CVD/
   stroke/BMI are not produced).
5. ✅ **Prospective kiosk validation** — protocol in
   [PROSPECTIVE_VALIDATION_PLAN.md](PROSPECTIVE_VALIDATION_PLAN.md) (linkage,
   reference standards, calibration/agreement analysis, exit criteria). The
   one-column linkage build is intentionally deferred to the study/ethics design.

None required a *new model for data gathering*; they harden the methodology
around the data the Brief already defines.
