"""Building the training export from a deployment's calibration corpus.

Paired rPPG-plus-reference captures are what the corrector actually trains on,
so ``rppg_calibration_records`` is the source. Each row carries the camera
measurement, the reference-device truth beside it, and the signal quality that
explains the gap — which is the whole training signal.

Two gates stand in front of it, and both fail closed:

* the organisation must have agreed, in a *named* version of an agreement, that
  de-identified records may leave (:func:`assert_export_permitted`);
* the result must survive k-anonymity with whole-class suppression
  (:mod:`victus_api.export.deidentify`).

The export deliberately carries **no organisation identifier**. Once records are
pooled they cannot be attributed back to a funder from their contents. That is a
real property and also a limited one: a file arriving from a funder's own
deployment is attributable at the transport layer regardless of what is inside
it. Closing that needs a pooling intermediary, which is an operational decision
rather than a code one. It is recorded in the DPIA as a residual risk rather
than quietly implied away here.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from victus_api.config import Settings
from victus_api.core.logging import get_logger
from victus_api.db.models import (
    Organisation,
    RppgCalibrationRecord,
    StudySubject,
)
from victus_api.export.deidentify import (
    ReleaseSpec,
    SuppressionReport,
    age_band,
    k_anonymise,
)
from victus_api.organisation.service import resolve_deployment_organisation

log = get_logger(__name__)

# The allowlist. Every field here was opted in deliberately; anything added to
# the underlying table in future is excluded until someone names it here.
#
# Note what is absent: the subject's Fitzpatrick grade is released only as a
# generalised quasi-identifier, and free-text (`notes`, device labels) never
# leaves at all — free text is where identifiers hide, and no amount of
# k-anonymity over structured columns helps if a note says "the nurse's cousin".
CALIBRATION_RELEASE = ReleaseSpec(
    release=frozenset(
        {
            # --- generalised quasi-identifiers ---
            "age_band",
            "sex",
            "site_code",
            "skin_tone_band",
            # --- camera measurement ---
            "rppg_hr_bpm",
            "rppg_rr_bpm",
            "rppg_hrv_rmssd_ms",
            "rppg_hrv_sdnn_ms",
            "rppg_quality",
            "rppg_method_selected",
            "rppg_snr_chrom_db",
            "rppg_snr_pos_db",
            "rppg_pipeline_version",
            # --- reference-device truth ---
            "reference_device_type",
            "reference_hr_bpm",
            "reference_rr_bpm",
            "reference_hrv_rmssd_ms",
            "reference_hrv_sdnn_ms",
        }
    ),
    quasi_identifiers=("age_band", "sex", "site_code", "skin_tone_band"),
)


class ExportNotPermittedError(RuntimeError):
    """The organisation has not agreed that de-identified records may leave.

    Never downgraded to a warning or an empty export. Silently returning zero
    rows would look identical to a deployment with no data, and the difference
    between "they said no" and "there was nothing" is the whole point.
    """


@dataclass
class TrainingExport:
    rows: list[dict[str, Any]]
    report: SuppressionReport
    organisation_code: str | None
    consent_version: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            # Deliberately no organisation identifier in the payload — see the
            # module docstring for what that does and does not achieve.
            "consent_version": self.consent_version,
            "suppression": self.report.to_dict(),
            "rows": self.rows,
        }


async def assert_export_permitted(
    db: AsyncSession, *, settings: Settings
) -> Organisation | None:
    """Confirm this deployment may export, returning the organisation if bound.

    An unbound deployment — Victus' own research and pilot instances — exports
    its own data and needs no organisation's permission. A bound deployment
    holds a funder's members' data and needs theirs, recorded against a named
    agreement version so it can be audited when the terms change.
    """
    org = await resolve_deployment_organisation(db, settings=settings)
    if org is None:
        return None

    if not org.training_export_consent:
        raise ExportNotPermittedError(
            f"Organisation '{org.org_code}' has not consented to de-identified "
            "data leaving this deployment. Export refused."
        )
    if not org.training_export_consent_version:
        raise ExportNotPermittedError(
            f"Organisation '{org.org_code}' is marked as consenting but names no "
            "agreement version, so what they agreed to cannot be established. "
            "Export refused."
        )
    return org


def _skin_tone_band(subject: StudySubject | None) -> str | None:
    """Coarsen recorded skin tone for release.

    Fitzpatrick is retained here as the *quasi-identifier* rather than as the
    analysis variable — a visible attribute an adversary plausibly knows. It is
    collapsed to light/mid/dark because the six-point grade is finer than the
    knowledge anyone actually has about a stranger, and finer categories only
    fragment the equivalence classes and force more suppression.
    """
    if subject is None or subject.fitzpatrick_scale is None:
        return None
    grade = subject.fitzpatrick_scale.value
    if grade in ("I", "II"):
        return "I-II"
    if grade in ("III", "IV"):
        return "III-IV"
    return "V-VI"


async def build_training_export(
    db: AsyncSession, *, settings: Settings, k: int | None = None
) -> TrainingExport:
    """Assemble the de-identified, k-anonymised calibration corpus."""
    org = await assert_export_permitted(db, settings=settings)

    spec = (
        CALIBRATION_RELEASE
        if k is None
        else ReleaseSpec(
            release=CALIBRATION_RELEASE.release,
            quasi_identifiers=CALIBRATION_RELEASE.quasi_identifiers,
            k=k,
        )
    )

    rows = (
        await db.execute(
            select(RppgCalibrationRecord, StudySubject).outerjoin(
                StudySubject, StudySubject.user_id == RppgCalibrationRecord.user_id
            )
        )
    ).all()

    generalised: list[dict[str, Any]] = []
    for record, subject in rows:
        # An anonymised subject has already had their record withdrawn from
        # identifiable use; it must not reappear in a release.
        if subject is not None and subject.anonymised_at is not None:
            continue
        generalised.append(
            {
                "age_band": age_band(subject.age_years if subject else None),
                "sex": subject.sex_assigned_at_birth.value if subject else None,
                "site_code": settings.site_code,
                "skin_tone_band": _skin_tone_band(subject),
                "rppg_hr_bpm": record.rppg_hr_bpm,
                "rppg_rr_bpm": record.rppg_rr_bpm,
                "rppg_hrv_rmssd_ms": record.rppg_hrv_rmssd_ms,
                "rppg_hrv_sdnn_ms": record.rppg_hrv_sdnn_ms,
                "rppg_quality": record.rppg_quality,
                "rppg_method_selected": record.rppg_method_selected,
                "rppg_snr_chrom_db": record.rppg_snr_chrom_db,
                "rppg_snr_pos_db": record.rppg_snr_pos_db,
                "rppg_pipeline_version": record.rppg_pipeline_version,
                "reference_device_type": record.reference_device_type.value,
                "reference_hr_bpm": record.reference_hr_bpm,
                "reference_rr_bpm": record.reference_rr_bpm,
                "reference_hrv_rmssd_ms": record.reference_hrv_rmssd_ms,
                "reference_hrv_sdnn_ms": record.reference_hrv_sdnn_ms,
            }
        )

    released, report = k_anonymise(generalised, spec=spec)

    log.info(
        "training_export_built",
        organisation=org.org_code if org else None,
        rows_in=report.rows_in,
        rows_released=report.rows_released,
        rows_suppressed=report.rows_suppressed,
        k=report.k,
    )

    return TrainingExport(
        rows=released,
        report=report,
        organisation_code=org.org_code if org else None,
        consent_version=org.training_export_consent_version if org else None,
    )


async def record_export_consent(
    db: AsyncSession,
    *,
    organisation_id: uuid.UUID,
    version: str,
    granted: bool,
) -> Organisation:
    """Record an organisation's decision on de-identified export.

    Withdrawal clears the version too: leaving a stale version beside a FALSE
    would suggest a live agreement that no longer holds.
    """
    org = await db.get(Organisation, organisation_id)
    if org is None:
        raise ExportNotPermittedError(f"No organisation {organisation_id}.")

    org.training_export_consent = granted
    org.training_export_consent_version = version if granted else None
    if granted:
        org.training_export_consent_at = datetime.now(UTC)
    else:
        org.training_export_consent_at = None
    await db.flush()
    return org
