# Enrollment — Data Protection Impact note

Scope: the front-of-platform participant **enrollment** step (`participant_profiles`)
that every participant completes before reaching either pathway (3B-Triage / TOI).
This note supports the HREC/POPIA/NDPA/CDPA submissions; it is not a substitute
for the site DPIA.

## What is captured, and why

| Field | Category | Purpose | Minimisation |
|---|---|---|---|
| Full name, email | Direct identifier | Contact / record linkage | Tombstoned on erasure |
| Patient/client ID | Direct identifier | Link to source system | **Never stored raw — salted SHA-256 only** |
| Age **range** | Quasi-identifier | Cohort stratification | Band, not exact age/DOB |
| Biological sex | Quasi-identifier | Clinical covariate | — |
| Region | Quasi-identifier | Jurisdiction + stratification | Country-level only |
| Race/ethnicity | Special category | Equity reporting | **Optional**, self-reported, separate from the physiological Fitzpatrick phototype used by TOI |
| Consent (triage, TOI, research) | — | Lawful basis | Granular; both pathways mandatory to enroll |

## Lawful basis & consent
Explicit, granular **consent** is captured *before* the data (recorded as
`consent_records`, version `enroll-v1`, timestamped, jurisdiction-stamped).
Consent to both the triage and TOI pathways is mandatory to enroll; research
data-sharing is optional. Adults only — the age vocabulary has no under-18 band
and the API rejects any other value.

## Jurisdiction
Region → governing regime is stamped at enrollment: **NG → NDPA, ZW → CDPA,
ZA → POPIA**, else OTHER. The participant's `site_code` is aligned so downstream
records inherit the same jurisdiction.

## Storage, access, retention
- **Access**: identified fields are returned only to the participant themselves
  and to CLINICIAN/ADMIN roles (RBAC); every access is audited.
- **Patient ID**: only the salted one-way hash is persisted — re-identification
  requires the issuing source system, not a read of our database.
- **Erasure** (GDPR Art. 17 / POPIA s24 / NDPA / CDPA): account erasure
  **nulls** name, email, race/ethnicity and the patient-ID hash and sets
  `erased_at`, while retaining only the **de-identified strata** (age band, sex,
  region, jurisdiction) under the research-retention exception.

## Residual risks & mitigations
- **Re-identification via quasi-identifiers** (age band × sex × region): coarse
  by design (bands, country-level region); acceptable for the retained,
  de-identified post-erasure record.
- **Special-category (race)**: optional and consented; must **not** be used as a
  model input or as a substitute for Fitzpatrick phototype (equity reporting only).
- **Posture change**: this is the platform's first identified store — it is
  RBAC-guarded, audited, consented, and erasure-covered from day one.
