"""Research-console HTTP layer — labelled triage capture for Model 1 training.

Role-gated to researchers (CHW / clinician / admin); patients cannot enter
ground-truth-labelled data. Pathway B (TOI) training data is captured by the
existing ``/calibration`` + ``/study`` routers.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import StreamingResponse

from victus_api.core.deps import DbSession, require_role
from victus_api.db.models import User, UserRole
from victus_api.research.importer import import_rows, parse_csv
from victus_api.research.schemas import (
    AcquisitionWorklistItem,
    ResearchCaseCreate,
    ResearchCaseResponse,
    ResearchCorpusStats,
    ResearchImportSummary,
)
from victus_api.research.service import (
    acquisition_worklist,
    corpus_stats,
    create_research_case,
    export_training_rows,
    list_research_cases,
)
from victus_api.triage.acquisition import AcquisitionPriority

router = APIRouter(prefix="/research", tags=["research"])

# Researchers only. The dependency both gates access and yields the actor.
Researcher = Annotated[
    User, Depends(require_role(UserRole.CHW, UserRole.CLINICIAN, UserRole.ADMIN))
]


@router.post(
    "/triage-cases",
    response_model=ResearchCaseResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record a ground-truth-labelled triage case for Model 1 training.",
)
async def create_case(
    payload: ResearchCaseCreate, user: Researcher, db: DbSession
) -> ResearchCaseResponse:
    return await create_research_case(db, payload=payload, created_by=user)


@router.post(
    "/triage-cases/import",
    response_model=ResearchImportSummary,
    summary="Bulk-import a REDCap/ODK/CSV field-study export into the corpus.",
)
async def import_cases(
    request: Request, user: Researcher, db: DbSession
) -> ResearchImportSummary:
    """Accepts a CSV body (REDCap/ODK export). Labels are auto-derived per row;
    invalid rows are reported individually without aborting the batch."""
    text = (await request.body()).decode("utf-8", errors="replace")
    rows = parse_csv(text)
    return await import_rows(db, raw_rows=rows, created_by=user)


@router.get("/triage-cases", response_model=list[ResearchCaseResponse])
async def list_cases(
    _user: Researcher,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[ResearchCaseResponse]:
    return await list_research_cases(db, limit=limit)


@router.get(
    "/triage-cases/stats",
    response_model=ResearchCorpusStats,
    summary="Corpus snapshot: counts, per-disease label distribution, coverage.",
)
async def stats(_user: Researcher, db: DbSession) -> ResearchCorpusStats:
    return await corpus_stats(db)


@router.get(
    "/acquisition-worklist",
    response_model=list[AcquisitionWorklistItem],
    summary=(
        "Active-learning worklist: participants ranked by how much confirmatory "
        "ground truth would improve the model (EDL uncertainty × decision "
        "boundary). Spend scarce lab tests where they are most informative."
    ),
)
async def acquisition(
    _user: Researcher,
    db: DbSession,
    min_priority: AcquisitionPriority = AcquisitionPriority.LOW,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[AcquisitionWorklistItem]:
    return await acquisition_worklist(db, limit=limit, min_priority=min_priority)


@router.get(
    "/triage-cases/export",
    summary="Stream the labelled corpus as JSONL for the training pipeline.",
)
async def export(_user: Researcher, db: DbSession) -> StreamingResponse:
    rows = await export_training_rows(db)

    async def _gen() -> AsyncIterator[bytes]:
        for row in rows:
            yield (json.dumps(row, separators=(",", ":")) + "\n").encode("utf-8")

    return StreamingResponse(
        _gen(),
        media_type="application/x-ndjson",
        headers={
            "Content-Disposition": "attachment; filename=victus-triage-corpus.jsonl"
        },
    )
