"""SITE_CODE must resolve to a data-protection regime before production boots.

The site code decides which law governs a participant's record. It is stamped
onto the row at creation and never revisited, so an instance that runs even
briefly on the wrong code produces records whose jurisdiction is wrong and
cannot be fixed by editing the environment afterwards.

The failure it guards against is silent rather than loud: an unmapped code does
not raise anywhere: ``jurisdiction_for_site`` returns the caller's *fallback*,
so a Zimbabwean pilot left on DEMO records participants under whatever regime
the fallback names instead of the CDPA, with nothing in any log to say so.
"""

from __future__ import annotations

import pytest

from victus_api.config import KNOWN_SITE_CODES, Settings
from victus_api.db.models import ErasureJurisdiction
from victus_api.governance.jurisdictions import jurisdiction_for_site


def _prod(site_code: str) -> Settings:
    """Production settings with every other placeholder already replaced, so the
    only thing under test is the site code."""
    return Settings(
        api_env="production",
        site_code=site_code,
        jwt_secret_key="a" * 48,
        internal_service_token="b" * 48,
        pseudo_salt="c" * 48,
        kiosk_encryption_key="d" * 64,
    )


@pytest.mark.parametrize("code", sorted(KNOWN_SITE_CODES))
def test_a_mapped_site_code_boots(code: str) -> None:
    _prod(code).assert_safe_for_production()


@pytest.mark.parametrize("code", ["DEMO", "DEFAULT", "", "XX", "zimbabwe"])
def test_an_unmapped_site_code_refuses_to_boot(code: str) -> None:
    with pytest.raises(RuntimeError, match="maps to no data-protection regime"):
        _prod(code).assert_safe_for_production()


def test_the_default_site_code_cannot_reach_production() -> None:
    # The shipped default is DEFAULT. Nothing about it looks wrong at a glance,
    # which is exactly why it needs to be rejected rather than trusted.
    assert Settings().site_code == "DEFAULT"
    with pytest.raises(RuntimeError, match="maps to no data-protection regime"):
        _prod("DEFAULT").assert_safe_for_production()


def test_site_code_is_accepted_case_insensitively() -> None:
    # jurisdiction_for_site upper-cases before lookup, so the guard must agree —
    # otherwise a lowercase "zw" would be refused at boot despite resolving to
    # the CDPA perfectly well at runtime.
    _prod("zw").assert_safe_for_production()
    assert (
        jurisdiction_for_site("zw", fallback=ErasureJurisdiction.GDPR)
        is ErasureJurisdiction.CDPA
    )


def test_development_is_unaffected() -> None:
    # Local work and the demo harness run on DEMO/DEFAULT and must keep working;
    # the guard is a production concern only.
    Settings(api_env="development", site_code="DEMO").assert_safe_for_production()
    Settings(api_env="test", site_code="DEFAULT").assert_safe_for_production()


def test_the_guard_list_matches_the_jurisdiction_table() -> None:
    """KNOWN_SITE_CODES is duplicated in config to keep it free of ORM imports.

    This is the test that makes the duplication safe: adding a country to the
    jurisdiction table without adding it here would refuse to boot a perfectly
    valid deployment, and removing one without updating here would let an
    unmapped code through.
    """
    for code in KNOWN_SITE_CODES:
        assert (
            jurisdiction_for_site(code, fallback=ErasureJurisdiction.GDPR)
            is not ErasureJurisdiction.GDPR
        ), f"{code} is allowed at boot but has no entry in the jurisdiction table"


def test_an_unmapped_code_silently_falls_back_rather_than_raising() -> None:
    # Pins the reason the guard has to exist at all. If this ever started
    # raising, the boot guard would be belt-and-braces instead of the only
    # thing standing between a misconfiguration and mislabelled records.
    assert (
        jurisdiction_for_site("DEMO", fallback=ErasureJurisdiction.GDPR)
        is ErasureJurisdiction.GDPR
    )
