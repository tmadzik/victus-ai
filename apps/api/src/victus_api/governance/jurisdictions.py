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
    "ZA": ErasureJurisdiction.POPIA,  # South Africa
    "ZW": ErasureJurisdiction.POPIA,  # Zimbabwe pilot — POPIA-modelled regime
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
