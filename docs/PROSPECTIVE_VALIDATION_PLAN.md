# Prospective Kiosk-Population Validation Plan

Purpose: close the improvement loop that the cross-sectional field study (the
*Victus Brief*) cannot, by measuring how the models perform **on the population
they are actually deployed to** — kiosk walk-ups — against facility-confirmed
ground truth. This is the study a reviewer will ask for before any clinical
claim; the field study trains the models, this study validates them in situ.

> This is a protocol, not code. It defines what to collect, how to link it, the
> endpoints, and the analysis. The one schema addition it needs is small and
> noted in §4.

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
  study's N.
- **Primary outcomes:** per-disease sensitivity/specificity/PPV/NPV at the
  deployed threshold; ROC-AUC; **calibration (ECE + reliability curve)**;
  for TOI, **Bland-Altman bias + 95 % limits of agreement**, stratified by
  Fitzpatrick (esp. V–VI) and by ambient-light condition (the kiosk confound the
  controlled calibration study does not capture).
- **Subgroups (pre-specified):** Fitzpatrick, sex, age band, site, urban/rural.

## 3. Consent & governance

Distinct from the anonymous kiosk wellness flow: this requires **explicit
research consent** (HREC/NHREC, POPIA/NDPA per [[feedback-zimbabwe-legislation]]
jurisdiction), because the kiosk capture is deliberately linked to identified
facility results. Reuse the existing study pre-registration + erasure machinery;
linkage identifiers live only in the consented research record and are erasable.

## 4. Linkage mechanism (small, deferred build)

A kiosk session already anchors a pseudonymous `users` row at consent. To link a
kiosk capture to its later facility-confirmed `research_triage_cases` row:

1. At kiosk completion, if the participant opts into the validation study, mint a
   short **validation linkage code** and show/send it with their result.
2. At the facility, the data collector enters that code alongside the confirmed
   labels (a new optional `validation_code` column on `research_triage_cases`,
   plus the kiosk `users.id` / `toi_assessments.id` it resolves to).
3. The analysis joins kiosk index predictions ↔ facility reference rows on the
   code.

Implementation is one nullable column + one lookup endpoint — intentionally
**not** built here, because the study/ethics design must lead the schema.

## 5. Analysis & retraining

- Compute §2 metrics overall and per subgroup on the **linked prospective set**
  using `training/evaluation.py` (ROC-AUC, ECE, reliability, Bland-Altman) with
  `group_holdout_split` for site/country generalisation.
- Emit an updated **model card** (`training/model_card.py`) recording the
  prospective metrics and the populations validated.
- **Recalibrate** (e.g., temperature scaling / per-site intercepts) on the
  prospective set before any threshold change; only then consider folding the
  newly-labelled, linked kiosk captures into the training corpus — which is the
  point at which "the kiosk improves the model" becomes literally true.

## 6. Exit criteria

A disease's kiosk claim is supportable only when, on the prospective set:
pre-specified sensitivity is met with its CI, calibration error is within the
agreed bound, and subgroup performance (notably Fitzpatrick V–VI) shows no
material disparity. Until then the surface stays **screening, not diagnosis**.
