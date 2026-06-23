"""Map a deployment site/country to its governing data-protection regime.

A participant's data-protection jurisdiction follows *where they were enrolled*,
not a free choice on the erasure form — a Nigerian participant falls under the
NDPA whatever the request body says. Unknown sites fall back to the caller's
default so the behaviour is never worse than before this mapping existed.
"""

from __future__ import annotations

from victus_api.db.models import ErasureJurisdiction

# Site codes are the per-instance `settings.site_code` stamped onto each User.
_SITE_JURISDICTION: dict[str, ErasureJurisdiction] = {
    "NG": ErasureJurisdiction.NDPA,   # Nigeria Data Protection Act 2023 (NDPC)
    "ZA": ErasureJurisdiction.POPIA,  # South Africa — POPIA
    "ZW": ErasureJurisdiction.CDPA,   # Zimbabwe — Cyber & Data Protection Act [Ch 12:07] (POTRAZ)
}


def jurisdiction_for_site(
    site_code: str | None, *, fallback: ErasureJurisdiction
) -> ErasureJurisdiction:
    """Resolve the data-protection jurisdiction for a deployment site code.

    Returns ``fallback`` for an unknown or missing site so an explicitly chosen
    jurisdiction (or the existing default) still wins where there is no mapping.
    """
    if not site_code:
        return fallback
    return _SITE_JURISDICTION.get(site_code.strip().upper(), fallback)


# --- Retention legal basis & participant-facing summary ---------------------
#
# Two separate strings derive from a jurisdiction:
#   * retention_basis        — the short legal citation recorded on the erasure
#     request row (DB column is String(500)); machine/audit-facing.
#   * retention_policy_summary — the longer prose shown to the participant on
#     /account/data explaining what erasure does and under which law.
# They must cite the participant's *own* regime, not a foreign one (Zimbabwe is
# the Cyber and Data Protection Act [Ch 12:07], never South Africa's POPIA).

# Short legal-basis citation for the de-identified-research retention, by regime.
_RETENTION_BASIS: dict[ErasureJurisdiction, str] = {
    ErasureJurisdiction.GDPR: "GDPR Article 17(3)(d) — retention for scientific research",
    ErasureJurisdiction.POPIA: "POPIA section 14(3) — retention for research purposes",
    ErasureJurisdiction.NDPA: (
        "Nigeria Data Protection Act 2023 — research-retention basis (regulator: NDPC)"
    ),
    ErasureJurisdiction.CDPA: (
        "Cyber and Data Protection Act [Chapter 12:07] — research-retention basis "
        "(POTRAZ); clinician-held records remain subject to the Health Professions "
        "Act [Chapter 27:19] confidentiality duty"
    ),
}
_DEFAULT_RETENTION_BASIS = (
    "Applicable data-protection law — research-retention basis"
)


def retention_basis(jurisdiction: ErasureJurisdiction) -> str:
    """Short legal-basis citation stored on the erasure request (<=500 chars)."""
    return _RETENTION_BASIS.get(jurisdiction, _DEFAULT_RETENTION_BASIS)


# The participant-facing summary is the basis clause wrapped in shared prose so
# every regime reads consistently and only the cited law differs.
_SUMMARY_PREFIX = (
    "On erasure, your PII (email, name, password) is tombstoned and your study "
    "subjects are anonymised via salted SHA-256. De-identified biometric records "
    "(triage assessments, TOI assessments, calibration pairs) are retained for "
    "research integrity "
)
_SUMMARY_SUFFIX = (
    " since they no longer identify you. Audit-log rows referencing your "
    "historical user_id are preserved as regulatory evidence that the erasure "
    "was honoured."
)
_HEALTH_PROFESSIONS_NOTE = (
    " Any records a clinician holds about you stay subject to the confidentiality "
    "duty under the Health Professions Act [Chapter 27:19]."
)

# Basis clause used inside the participant summary (reads as a sentence fragment).
_SUMMARY_BASIS_CLAUSE: dict[ErasureJurisdiction, str] = {
    ErasureJurisdiction.GDPR: "under GDPR Article 17(3)(d) (retention for scientific research)",
    ErasureJurisdiction.POPIA: "under POPIA section 14(3) (retention for research purposes)",
    ErasureJurisdiction.NDPA: (
        "under the Nigeria Data Protection Act 2023 research-retention basis "
        "(regulator: NDPC)"
    ),
    ErasureJurisdiction.CDPA: (
        "under the Cyber and Data Protection Act [Chapter 12:07] research-retention "
        "basis, supervised by POTRAZ as Zimbabwe's Data Protection Authority"
    ),
}
_DEFAULT_SUMMARY_BASIS_CLAUSE = (
    "under the applicable data-protection law's research-retention basis"
)
# Regimes that append the clinician-confidentiality note to the summary.
_SUMMARY_EXTRA: dict[ErasureJurisdiction, str] = {
    ErasureJurisdiction.CDPA: _HEALTH_PROFESSIONS_NOTE,
}


def retention_policy_summary(jurisdiction: ErasureJurisdiction) -> str:
    """Participant-facing prose for /account/data, citing the right regime."""
    clause = _SUMMARY_BASIS_CLAUSE.get(jurisdiction, _DEFAULT_SUMMARY_BASIS_CLAUSE)
    extra = _SUMMARY_EXTRA.get(jurisdiction, "")
    return _SUMMARY_PREFIX + clause + _SUMMARY_SUFFIX + extra
