"""Cohort-level reporting for an organisation, with small-cell suppression.

This is the default view a funder sees: how many members were screened, how they
distribute across triage states, and whether the referral loop actually closes.
It answers the questions the pathway is sold on without naming anybody.

Aggregates are not automatically safe. A breakdown cell containing one person
discloses that person to anyone who knows roughly who is in the cohort, and a
funder knows its own membership exactly — which makes small cells more
disclosive here than in a public statistical release, not less. So every
breakdown goes through the same disclosure control as the training export
(:mod:`victus_api.export.deidentify`), including the complementary suppression
that stops a lone blanked cell being recovered by subtracting from the total.

The care-loop funnel is deliberately reused rather than recomputed: it is the
platform's existing measure of whether screening leads to treatment, and having
one definition of "attended" shared by the clinical and funder views is worth
more than a bespoke one here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from victus_api.db.models import (
    StudySubject,
    TriageAssessment,
    TriageState,
    User,
    UserRole,
)
from victus_api.export.deidentify import (
    K_DEFAULT,
    age_band,
    suppress_small_cells,
)
from victus_api.referrals.service import care_loop_stats

# The same k as the training export. A member is no less identifiable on a
# dashboard than in a file, and two different thresholds would only invite the
# question of which one is right.
COHORT_K = K_DEFAULT


@dataclass
class CohortReport:
    members_screened: int
    triage_distribution: dict[str, int | None]
    by_age_band: dict[str, int | None]
    by_sex: dict[str, int | None]
    care_loop: dict[str, Any]
    suppression: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "members_screened": self.members_screened,
            "triage_distribution": self.triage_distribution,
            "by_age_band": self.by_age_band,
            "by_sex": self.by_sex,
            "care_loop": self.care_loop,
            "suppression": self.suppression,
        }


async def build_cohort_report(db: AsyncSession, *, k: int = COHORT_K) -> CohortReport:
    """Aggregate this deployment's members, suppressing every small cell.

    No organisation filter appears anywhere in these queries, and that is
    correct rather than an omission: the deployment *is* the organisation. The
    boundary is enforced at boot and at write time
    (:mod:`victus_api.organisation.service`), so there is no cross-organisation
    row to exclude and no filter for a future query to forget.
    """
    members_screened = int(
        await db.scalar(
            select(func.count(func.distinct(TriageAssessment.user_id)))
        )
        or 0
    )

    triage_counts = {state.value: 0 for state in TriageState}
    for state, count in (
        await db.execute(
            select(TriageAssessment.state, func.count(TriageAssessment.id))
            .group_by(TriageAssessment.state)
        )
    ).all():
        triage_counts[state.value] = int(count)

    age_counts: dict[str, int] = {}
    sex_counts: dict[str, int] = {}
    for age_years, sex in (
        await db.execute(
            select(StudySubject.age_years, StudySubject.sex_assigned_at_birth).where(
                StudySubject.anonymised_at.is_(None)
            )
        )
    ).all():
        band = age_band(age_years) or "unknown"
        age_counts[band] = age_counts.get(band, 0) + 1
        sex_counts[sex.value] = sex_counts.get(sex.value, 0) + 1

    triage_out, triage_report = suppress_small_cells(triage_counts, k=k)
    age_out, age_report = suppress_small_cells(age_counts, k=k)
    sex_out, sex_report = suppress_small_cells(sex_counts, k=k)

    loop = await care_loop_stats(db)

    return CohortReport(
        members_screened=members_screened,
        triage_distribution=triage_out,
        by_age_band=age_out,
        by_sex=sex_out,
        care_loop=loop.model_dump(),
        suppression={
            "triage_distribution": triage_report.to_dict(),
            "by_age_band": age_report.to_dict(),
            "by_sex": sex_report.to_dict(),
        },
    )


@dataclass
class FlaggedMember:
    """One member a care manager may route into care.

    Named, by design — routing somebody into a wellness programme requires
    knowing who they are. This is exactly the payload the attestation gates, and
    every retrieval of it is written to the audit log.
    """

    user_id: str
    triage_state: str
    assessed_at: str


async def list_flagged_members(
    db: AsyncSession, *, states: tuple[TriageState, ...], limit: int = 200
) -> list[FlaggedMember]:
    """Members whose most recent triage landed in ``states``.

    No suppression here, and none is possible: the caller has asked for
    individuals and will receive individuals. The control on this path is the
    attestation and the audit record, not statistical disclosure control —
    which is why the two paths are separate functions rather than one function
    with a flag, where the wrong default would silently name people.
    """
    newest = (
        select(
            TriageAssessment.user_id.label("user_id"),
            func.max(TriageAssessment.created_at).label("latest"),
        )
        .group_by(TriageAssessment.user_id)
        .subquery()
    )

    rows = (
        await db.execute(
            select(TriageAssessment)
            .join(
                newest,
                (TriageAssessment.user_id == newest.c.user_id)
                & (TriageAssessment.created_at == newest.c.latest),
            )
            .join(User, User.id == TriageAssessment.user_id)
            .where(
                TriageAssessment.state.in_(states),
                User.erased_at.is_(None),
                User.role == UserRole.PATIENT,
            )
            .order_by(TriageAssessment.created_at.desc())
            .limit(limit)
        )
    ).scalars().all()

    return [
        FlaggedMember(
            user_id=str(row.user_id),
            triage_state=row.state.value,
            assessed_at=row.created_at.isoformat(),
        )
        for row in rows
    ]
