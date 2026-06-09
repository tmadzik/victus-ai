"""Study HTTP layer — subjects + sessions."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status

from victus_api.core.deps import CurrentUser, DbSession, require_consent, require_role
from victus_api.db.models import ConsentType, UserRole
from victus_api.study.schemas import (
    CreateSubjectRequest,
    EndSessionRequest,
    StartSessionRequest,
    StudySessionResponse,
    StudySubjectResponse,
)
from victus_api.study.service import (
    create_subject,
    end_session,
    get_active_session,
    get_session,
    get_subject,
    list_sessions,
    list_subjects,
    start_session,
)

router = APIRouter(prefix="/study", tags=["study"])


def _client_metadata(request: Request) -> tuple[str | None, str | None]:
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    return ip, (ua[:512] if ua else None)


# --- Subjects ----------------------------------------------------------------


@router.post(
    "/subjects",
    response_model=StudySubjectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Enrol an anonymous study subject.",
)
async def create_subject_endpoint(
    payload: CreateSubjectRequest,
    request: Request,
    db: DbSession,
    user: Annotated[
        CurrentUser, Depends(require_role(UserRole.CLINICIAN, UserRole.ADMIN, UserRole.CHW))
    ],
    _consent: Annotated[
        CurrentUser, Depends(require_consent(ConsentType.TOI_IMAGING))
    ],
) -> StudySubjectResponse:
    ip, ua = _client_metadata(request)
    return await create_subject(
        db, user=user, payload=payload, ip_address=ip, user_agent=ua
    )


@router.get(
    "/subjects",
    response_model=list[StudySubjectResponse],
    summary="List enrolled subjects for the authenticated researcher.",
)
async def list_subjects_endpoint(
    db: DbSession,
    user: Annotated[
        CurrentUser, Depends(require_role(UserRole.CLINICIAN, UserRole.ADMIN, UserRole.CHW))
    ],
    _consent: Annotated[
        CurrentUser, Depends(require_consent(ConsentType.TOI_IMAGING))
    ],
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> list[StudySubjectResponse]:
    return await list_subjects(db, user_id=user.id, limit=limit)


@router.get(
    "/subjects/{subject_id}",
    response_model=StudySubjectResponse,
    summary="Fetch a specific subject by id.",
)
async def get_subject_endpoint(
    subject_id: uuid.UUID,
    db: DbSession,
    user: Annotated[
        CurrentUser, Depends(require_role(UserRole.CLINICIAN, UserRole.ADMIN, UserRole.CHW))
    ],
    _consent: Annotated[
        CurrentUser, Depends(require_consent(ConsentType.TOI_IMAGING))
    ],
) -> StudySubjectResponse:
    return await get_subject(db, user_id=user.id, subject_id=subject_id)


# --- Sessions ---------------------------------------------------------------


@router.post(
    "/sessions",
    response_model=StudySessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary=(
        "Start a new session for a subject. Auto-ends any prior active "
        "session for this researcher so at most one is active at a time."
    ),
)
async def start_session_endpoint(
    payload: StartSessionRequest,
    request: Request,
    db: DbSession,
    user: Annotated[
        CurrentUser, Depends(require_role(UserRole.CLINICIAN, UserRole.ADMIN, UserRole.CHW))
    ],
    _consent: Annotated[
        CurrentUser, Depends(require_consent(ConsentType.TOI_IMAGING))
    ],
) -> StudySessionResponse:
    ip, ua = _client_metadata(request)
    return await start_session(
        db, user=user, payload=payload, ip_address=ip, user_agent=ua
    )


@router.get(
    "/sessions/active",
    response_model=StudySessionResponse | None,
    summary="Return the researcher's currently active (un-ended) session, if any.",
)
async def active_session_endpoint(
    db: DbSession,
    user: Annotated[
        CurrentUser, Depends(require_role(UserRole.CLINICIAN, UserRole.ADMIN, UserRole.CHW))
    ],
    _consent: Annotated[
        CurrentUser, Depends(require_consent(ConsentType.TOI_IMAGING))
    ],
) -> StudySessionResponse | None:
    return await get_active_session(db, user_id=user.id)


@router.get(
    "/sessions",
    response_model=list[StudySessionResponse],
    summary="List recent sessions for the researcher.",
)
async def list_sessions_endpoint(
    db: DbSession,
    user: Annotated[
        CurrentUser, Depends(require_role(UserRole.CLINICIAN, UserRole.ADMIN, UserRole.CHW))
    ],
    _consent: Annotated[
        CurrentUser, Depends(require_consent(ConsentType.TOI_IMAGING))
    ],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[StudySessionResponse]:
    return await list_sessions(db, user_id=user.id, limit=limit)


@router.get(
    "/sessions/{session_id}",
    response_model=StudySessionResponse,
    summary="Fetch a session by id.",
)
async def get_session_endpoint(
    session_id: uuid.UUID,
    db: DbSession,
    user: Annotated[
        CurrentUser, Depends(require_role(UserRole.CLINICIAN, UserRole.ADMIN, UserRole.CHW))
    ],
    _consent: Annotated[
        CurrentUser, Depends(require_consent(ConsentType.TOI_IMAGING))
    ],
) -> StudySessionResponse:
    return await get_session(db, user_id=user.id, session_id=session_id)


@router.post(
    "/sessions/{session_id}/end",
    response_model=StudySessionResponse,
    summary="End a session (idempotent).",
)
async def end_session_endpoint(
    session_id: uuid.UUID,
    payload: EndSessionRequest,
    request: Request,
    db: DbSession,
    user: Annotated[
        CurrentUser, Depends(require_role(UserRole.CLINICIAN, UserRole.ADMIN, UserRole.CHW))
    ],
    _consent: Annotated[
        CurrentUser, Depends(require_consent(ConsentType.TOI_IMAGING))
    ],
) -> StudySessionResponse:
    ip, ua = _client_metadata(request)
    return await end_session(
        db,
        user=user,
        session_id=session_id,
        payload=payload,
        ip_address=ip,
        user_agent=ua,
    )
