"""Site → data-protection jurisdiction mapping (pure, no DB)."""

from __future__ import annotations

from victus_api.db.models import ErasureJurisdiction
from victus_api.governance.jurisdictions import jurisdiction_for_site


def test_nigeria_maps_to_ndpa() -> None:
    assert (
        jurisdiction_for_site("NG", fallback=ErasureJurisdiction.GDPR)
        == ErasureJurisdiction.NDPA
    )


def test_zimbabwe_maps_to_cdpa() -> None:
    # Zimbabwe is governed by the Cyber and Data Protection Act [Ch 12:07],
    # not South Africa's POPIA.
    for site in ("ZW", "zw", " zw "):  # case/whitespace-insensitive
        assert (
            jurisdiction_for_site(site, fallback=ErasureJurisdiction.OTHER)
            == ErasureJurisdiction.CDPA
        )


def test_south_africa_maps_to_popia() -> None:
    assert (
        jurisdiction_for_site("ZA", fallback=ErasureJurisdiction.OTHER)
        == ErasureJurisdiction.POPIA
    )


def test_unknown_or_missing_site_uses_fallback() -> None:
    assert (
        jurisdiction_for_site("DEFAULT", fallback=ErasureJurisdiction.GDPR)
        == ErasureJurisdiction.GDPR
    )
    assert (
        jurisdiction_for_site(None, fallback=ErasureJurisdiction.POPIA)
        == ErasureJurisdiction.POPIA
    )
    assert (
        jurisdiction_for_site("", fallback=ErasureJurisdiction.OTHER)
        == ErasureJurisdiction.OTHER
    )
