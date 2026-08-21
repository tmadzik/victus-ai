# Data Protection Impact note — enrollment, skin tone & optical capture

Scope: the front-of-platform participant **enrollment** step
(`participant_profiles`) that every participant completes before reaching either
pathway, **plus** the skin-tone and optical data the TOI pathway and the
validation rail collect. This note supports the HREC/POPIA/NDPA/CDPA
submissions; it is not a substitute for the site DPIA.

> **Scope widened (skin tone).** `PROSPECTIVE_VALIDATION_PLAN.md` §3 retires
> Fitzpatrick as the analysis variable in favour of instrument-measured **ITA°**
> and **Monk Skin Tone**. An instrument reading of skin pigmentation is a
> materially different proposition from the optional self-reported
> `race_ethnicity` field this note originally covered, so §§3–4 below are new.
> The filename is retained so existing cross-references resolve.

> **Build status.** The `monk_skin_tone` and `ita_forehead_degrees` columns are
> **not yet built** (validation plan §5 defers them deliberately, so ethics leads
> schema). This note is the prospective assessment that must be accepted
> *before* they are added.

## 1. What is captured, and why

| Field | Category | Purpose | Minimisation |
|---|---|---|---|
| Full name, email | Direct identifier | Contact / record linkage | Tombstoned on erasure |
| Patient/client ID | Direct identifier | Link to source system | **Never stored raw — salted SHA-256 only** |
| Age **range** | Quasi-identifier | Cohort stratification | Band, not exact age/DOB |
| Biological sex | Quasi-identifier | Clinical covariate | — |
| Region | Quasi-identifier | Jurisdiction + stratification | Country-level only |
| Race/ethnicity | Special category | Equity **reporting** | **Optional**, self-reported, **never a model input** (§3.3) |
| Fitzpatrick phototype | Physiological / see §3.1 | Literature comparability | Optional; **demoted to secondary** |
| **Monk Skin Tone (1–10)** | See §3.1 | Recruitment quotas, subgroup reporting | Validation rail only; collector-assigned |
| **ITA° (forehead)** | See §3.1 | Continuous fairness analysis; corrector-model feature | Validation rail only; instrument-measured |
| Consent (triage, TOI, research) | — | Lawful basis | Granular; both pathways mandatory to enroll |

## 2. Lawful basis & consent

Explicit, granular **consent** is captured *before* the data (recorded as
`consent_records`, version `enroll-v1`, timestamped, jurisdiction-stamped).
Consent to both the triage and TOI pathways is mandatory to enroll; research
data-sharing is optional. Adults only — the age vocabulary has no under-18 band
and the API rejects any other value.

**Skin tone sits under two different bases depending on the rail:**

| Rail | Data | Basis |
|---|---|---|
| Field product (TOI capture) | Optional self-reported Fitzpatrick | `TOI_IMAGING` consent |
| Validation rail | MST + ITA°, collector-assigned | **Separate study-protocol consent** under HREC/NHREC approval, versioned in `study_subjects.consent_protocol_version` |

Instrument-measured pigmentation is **not** collected under the ordinary
`TOI_IMAGING` consent. It requires the study consent, and that consent must name
it explicitly — a participant agreeing to a wellness scan has not thereby agreed
to have their skin measured with a colourimeter for research.

## 3. Skin tone — the special-category assessment

### 3.1 Classification

Skin pigmentation is not, in itself, racial or ethnic origin. But a precise
measurement of it can **reveal or strongly proxy** racial or ethnic origin, and
the prudent position — the one taken here — is to handle ITA° and MST under the
**special-category / sensitive-personal-data** provisions of each regime:
POPIA s26 (race or ethnic origin), the NDPA's sensitive-personal-data
categories, and the ZW CDPA's sensitive-data categories.

We do **not** claim these values are biometric data in the strict sense: skin
tone alone does not permit unique identification of an individual, which is the
threshold most regimes set for biometric data. It is treated as sensitive, not
as an identifier.

### 3.2 Necessity — why this is collectable at all

Data minimisation requires that we justify collecting a sensitive value rather
than simply asserting a benefit. The justification here is unusually direct:

> The platform's central equity claim is that **performance does not degrade on
> darker skin**. That claim cannot be evidenced without measuring skin tone. The
> alternative to collecting it is not a less intrusive study — it is an
> unevidenced claim about a population that has historically borne the cost of
> exactly this omission in optical medical devices.

Collecting it is therefore *necessary for the purpose*, and the purpose —
demonstrating the device works for the population it is sold to — is one the
data subject shares.

### 3.3 Race is not pigmentation, and the platform must not conflate them

This distinction is load-bearing and is enforced in code review:

| | `race_ethnicity` | ITA° / MST |
|---|---|---|
| Nature | **Social** category | **Optical** property of the tissue measured |
| Source | Self-reported, optional | Instrument / trained collector |
| Model input | **Never** | **Yes** — the corrector's pigmentation feature |
| Use | Equity reporting only | Fairness analysis + signal correction |

Pigmentation is a legitimate model input because melanin absorption physically
determines how much plethysmographic signal survives at the sensor; it is a
property of the measurement, not of the person's identity. A social category
must never stand in for it, and a physical measurement must never be reported as
if it were a social category.

### 3.4 Collection controls

- **Site:** forehead ROI — the skin the camera actually reads (validation plan
  §3.3). An inner-arm constitutive reading may be taken as secondary.
- **Assignment:** trained collector under specified lighting. Self-reported MST
  is acceptable in the field product but **not** in the validation rail.
- **Storage:** `study_subjects.monk_skin_tone` (stable descriptor, on a table
  that by design holds **no PII**); `rppg_calibration_records.ita_forehead_degrees`
  (measured per capture, because facultative pigment varies over time).
- **Access:** RBAC-guarded to CLINICIAN/ADMIN and the participant; every read
  audited, as for all identified fields.

## 4. Optical capture — what the camera does and does not retain

The single question a reviewer will ask first is what happens to the video. It
is answered by the architecture, not by policy:

- **No frame, face image or video is ever written to storage** — on either the
  browser TOI wizard or the kiosk terminal. Extraction runs in the page; only
  per-frame ROI **colour means** are transmitted.
- The kiosk persists **derived acquisition quality only** —
  `signal_quality_index`, `illumination_score`, `face_bbox_ratio`,
  `frame_count`, `error_flags` (`kiosk_biometric_metadata`). None of these
  reconstruct an image.
- The rPPG traces that ride the processing job are **scrubbed on completion**.
- The participant-facing result is sealed **AES-256-GCM** at rest, released
  through a single-use OTP-gated link, and the ciphertext is **purged once
  viewed or expired**.

Because no facial image is retained, the platform does not process biometric
data for identification purposes at any point in the capture path.

## 5. Jurisdiction

Region → governing regime is stamped at enrollment: **NG → NDPA, ZW → CDPA,
ZA → POPIA**, else OTHER. The participant's `site_code` is aligned so downstream
records inherit the same jurisdiction.

## 6. Storage, access, retention

- **Access**: identified fields are returned only to the participant themselves
  and to CLINICIAN/ADMIN roles (RBAC); every access is audited.
- **Patient ID**: only the salted one-way hash is persisted — re-identification
  requires the issuing source system, not a read of our database.
- **Erasure** (GDPR Art. 17 / POPIA s24 / NDPA / CDPA): account erasure nulls
  `full_name`, `email`, `race_ethnicity` and `patient_id_hash` on
  `participant_profiles`, tombstones the `users` row, deletes linked WhatsApp
  and kiosk sessions, scrubs queued jobs, and anonymises linked study subjects —
  retaining only the **de-identified strata** (age band, sex, region,
  jurisdiction) under the research-retention exception.
- **Skin tone on erasure — retained as a de-identified stratum.** Subject
  anonymisation pseudonymises `external_subject_id` and clears
  `medical_history_summary`, `height_cm` and `weight_kg`, while **retaining**
  age, sex and phototype as research strata. MST and ITA° follow that existing
  precedent, for a specific reason: by that point the row carries no identifiers,
  and **destroying the pigmentation variable would retrospectively invalidate the
  fairness analysis** that justified collecting it. Participants are told this at
  consent.

## 7. Organisation deployments and the training export

Added when the funder / insurer pathway was built. It describes a **new data
flow to a new category of recipient**, which is what triggers a DPIA revision
rather than a note.

### 7.1 The arrangement

A funder, insurer or employer ("the organisation") has members screened by
Victus. Tenancy is a **deployment boundary**: one instance, one database, one
organisation, with no cross-organisation query path in the software at all. The
organisation is the controller for its members' screening data; Victus operates
the deployment.

Separately, and only with the organisation's agreement, a **de-identified
extract** of paired camera-and-reference captures leaves the deployment to
improve the models. This section is about that extract.

### 7.2 Why the existing anonymisation path was not reused

`governance/anonymiser.py` is titled "Pure pseudonymisation helpers" and is
exactly that: a salted SHA-256 over the subject id, with the deployment holding
the salt. Anyone holding the salt and a candidate list of subjects can reverse
it. **That remains personal data** under POPIA, the NDPA and the Cyber and Data
Protection Act, and it must not be described to an organisation as anonymised.

It is the right mechanism for erasure-with-continuity, where a stable link is
the point. It is the wrong mechanism for release, where the absence of a link is
the point. The export therefore uses a separate pipeline (`export/deidentify.py`)
and shares no code path with it.

### 7.3 Controls applied to the extract

| Control | What it does |
|---|---|
| **Allowlist projection** | Only explicitly named fields are emitted. A denylist would fail open the moment a column is added to the source table; this fails closed. |
| **Never-release set** | Direct identifiers and relinking keys are rejected even if a developer adds them to the allowlist. |
| **Free-text exclusion** | `notes`, `medical_history_summary` and device labels never leave. Structured k-anonymity cannot help if a note names a person. |
| **Generalisation** | Age is banded and top-coded at 80+; skin tone is coarsened from the six-point grade to three bands. |
| **k-anonymity, k = 5** | Rows are grouped on (age band, sex, site, skin-tone band). Any class below k is dropped. |
| **Whole-class suppression** | No partial release — released remnants of a small class would form a small class of their own. |
| **Consent gate** | Refuses unless the organisation has agreed under a **named agreement version**, so what was agreed can be established after the terms change. |
| **Withdrawal** | Clears the version as well as the flag, so no stale agreement appears live. |
| **Erasure honoured** | Subjects already anonymised under §6 are excluded from every extract. |
| **Suppression report** | Ships with the data. Suppression falls hardest on small subgroups, so a recipient must be able to distinguish a thin cohort from a biased one. |

### 7.4 Assumptions this rests on

Stated plainly, because they are what a re-identification assessment must test:

1. **Skin tone is treated as a quasi-identifier**, not as a sensitive attribute.
   An adversary is assumed to be able to observe it. This is why it is banded
   and included in the k computation.
2. **Instrument-measured ITA°, once collected, is treated as a released
   measurement rather than a quasi-identifier.** The assumption is that no
   adversary holds colourimeter readings of a target. This assumption is the
   weakest one here and should be revisited if ITA is ever recorded anywhere a
   third party can obtain it.
3. **The recipient is not assumed hostile,** but is assumed to hold ordinary
   population data (age, sex, region). k = 5 is calibrated to that, not to an
   adversary with a member roster.

### 7.5 Residual risks not closed by the software

1. **Transport-layer attribution.** The extract carries no organisation
   identifier, so pooled records cannot be attributed from their contents. But a
   file arriving from an organisation's own deployment is attributable by the
   fact of its arrival. Closing this needs a pooling intermediary or a
   trusted third party — an operational arrangement, not a code change. **Until
   that exists, "not linked to the organisation" is true of the data and not of
   the transfer, and must be described that way to organisations.**
2. **Differencing across releases.** Two extracts taken at different times can be
   subtracted to isolate the rows added between them, and a small difference set
   may fall below k even though each release satisfied it. Mitigation is
   procedural — fix a cohort definition per release, or re-run k over the union.
   Not currently enforced in code.
3. **k-anonymity does not prevent attribute disclosure.** If every member of an
   equivalence class shares a screening outcome, membership of the class reveals
   the outcome without identifying the individual. l-diversity would address
   this and is not implemented.
4. **No formal re-identification risk assessment has been performed.** Until one
   is, the extract should be described as **de-identified**, not anonymous, and
   handled as personal data by agreement.

### 7.6 What must not be said

The extract may not be described to an organisation, a regulator or an ethics
committee as "anonymous" or "anonymised" until §7.5 item 4 is discharged. The
accurate description is: *de-identified to a k-anonymity threshold of 5 with
whole-class suppression, carrying no direct identifiers and no organisation
identifier, subject to the residual risks in §7.5.*

## 8. Residual risks & mitigations

- **Re-identification via quasi-identifiers** (age band × sex × region): coarse
  by design (bands, country-level region); acceptable for the retained,
  de-identified post-erasure record.
- **Pigmentation increases the quasi-identifier surface.** Adding a 10-point MST
  and a continuous ITA° to a small cohort narrows the field further than age ×
  sex × region alone. Mitigation: pigmentation is retained only on rows already
  stripped of identifiers, and **published outputs report banded MST, never
  per-subject ITA°**.
- **Special-category (race)**: optional and consented; **never** a model input
  and never used as a proxy for measured pigmentation (§3.3).
- **Function creep**: a measured pigmentation value is exactly the sort of field
  that later attracts uses nobody consented to. It is scoped to fairness
  analysis and signal correction; any new use requires a fresh DPIA entry and a
  consent-version bump, not a code review.
- **Posture change**: this remains the platform's first identified store — RBAC-
  guarded, audited, consented, and erasure-covered from day one.

## 9. Open items before enrolment

1. **HREC/NHREC submission** must name ITA°/MST collection explicitly, including
   the colourimeter, the forehead site, and the retention-through-anonymisation
   position in §6.
2. **Consent copy** (`study_subjects.consent_protocol_version`) must be revised
   and re-versioned to describe the measurement in plain language.
3. **Schema + corrector retrain** per validation plan §5 — this note must be
   accepted first.
4. **Legal review per jurisdiction** of the §3.1 classification. The prudent
   position is taken here; local counsel should confirm it for ZW, NG and ZA.
5. **Re-identification risk assessment** of the §7 training extract, against the
   assumptions in §7.4 and the residual risks in §7.5, signed by someone
   accountable. Until it is discharged the extract is **de-identified, not
   anonymous** (§7.6), and no agreement, pitch or ethics submission may describe
   it otherwise.
6. **Transport-layer attribution** (§7.5 item 1) needs an operational answer —
   pooling intermediary or trusted third party — before an organisation is told
   its contribution is unattributable. The software cannot close this.

> **Section numbering changed.** The training-export section was inserted as §7,
> moving residual risks to §8 and this list to §9. Earlier references to
> "§8 item 3" for the schema/corrector precondition mean **§9 item 3** below.
