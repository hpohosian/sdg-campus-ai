from fastapi import APIRouter, Depends

from chatbot.schemas import CreateSessionRequest, SessionResponse
from chatbot.services.session_service import SessionService
from dependencies import get_session_service


router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=SessionResponse)
async def create_session(
    request: CreateSessionRequest,
    service: SessionService = Depends(get_session_service),
):
    session = await service.create_session(
        user_id=request.user_id,
        course_id=request.course_id,
        title=request.title,
    )

    return SessionResponse(
        session_id=session['session_id'],
        user_id=session['user_id'],
        course_id=session['course_id'],
        title=session['title'],
    )
