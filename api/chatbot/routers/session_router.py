from fastapi import APIRouter, Depends, HTTPException, Query

from chatbot.schemas import CreateSessionRequest, SessionResponse
from chatbot.services.session_service import SessionService
from dependencies import get_session_service, get_current_user_id


router = APIRouter(prefix="/sessions", tags=["sessions"])


# =========================
# CREATE SESSION
# =========================
@router.post("", response_model=SessionResponse)
async def create_session(
    request: CreateSessionRequest,
    user_id: int = Depends(get_current_user_id),
    service: SessionService = Depends(get_session_service),
):
    resolved_user_id = user_id if user_id else request.user_id

    session = await service.create_session(
        user_id=resolved_user_id,
        course_id=request.course_id,
        title=request.title,
    )

    return SessionResponse(
        session_id=session.session_id,
        user_id=session.user_id,
        course_id=session.course_id,
        title=session.title,
        is_active=session.is_active
    )
    

# =========================
# GET ONE SESSION
# =========================
@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: str,
    user_id: int = Depends(get_current_user_id),
    service: SessionService = Depends(get_session_service),
):
    session = await service.get_session(session_id)

    # protection: you can’t watch other people’s sessions
    if session.user_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    return SessionResponse(
        session_id=session.session_id,
        user_id=session.user_id,
        course_id=session.course_id,
        title=session.title,
        is_active=session.is_active
    )


# =========================
# GET USER SESSIONS
# =========================
@router.get("", response_model=list[SessionResponse])
async def get_user_sessions(
    user_id: int = Depends(get_current_user_id),
    service: SessionService = Depends(get_session_service),
):
    sessions = await service.get_user_sessions(user_id)

    return [
        SessionResponse(
            session_id=s.session_id,
            user_id=s.user_id,
            course_id=s.course_id,
            title=s.title,
            is_active=s.is_active
        )
        for s in sessions
    ]


# =========================
# UPDATE SESSION
# =========================
@router.put("/{session_id}", response_model=SessionResponse)
async def update_session(
    session_id: str,
    request: CreateSessionRequest,
    user_id: int = Depends(get_current_user_id),
    service: SessionService = Depends(get_session_service),
):
    session = await service.get_session(session_id)

    if session.user_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    updated = await service.update_session(
        session_id=session_id,
        title=request.title,
    )

    return SessionResponse(
        session_id=updated.session_id,
        user_id=updated.user_id,
        course_id=updated.course_id,
        title=updated.title,
        is_active=updated.is_active
    )


# =========================
# ARCHIVE SESSION
# =========================
@router.put("/archive/{session_id}")
async def archive_session(
    session_id: str,
    user_id: int = Depends(get_current_user_id),
    service: SessionService = Depends(get_session_service),
):
    session = await service.get_session(session_id)

    if session.user_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    await service.archive_session(session_id)

    return {
        "session_id": session_id,
        "status": "archived"
    }


# =========================
# DEARCHIVE SESSION
# =========================
@router.put("/dearchive/{session_id}")
async def archive_session(
    session_id: str,
    user_id: int = Depends(get_current_user_id),
    service: SessionService = Depends(get_session_service),
):
    session = await service.get_session(session_id)

    if session.user_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    await service.dearchive_session(session_id)

    return {
        "session_id": session_id,
        "status": "dearchived"
    }


# =========================
# DELETE SESSION
# =========================
@router.delete("/{session_id}")
async def delete_session(
    session_id: str,
    service: SessionService = Depends(get_session_service),
):
    try:
        await service.delete_session(session_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "status": "deleted permanently"
    }