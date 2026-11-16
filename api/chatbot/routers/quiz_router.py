"""
Quiz endpoints (see chatbot/quiz/service.py).

    POST /sessions/{session_id}/quiz
        {"scope": "course"|"chat", "count": 3|5|10|20, "topic": "...", "language": "de"}
        -> {"request": MessageResponse, "quiz": MessageResponse, "title": str|null}
        Generates the quiz (takes ~10-30 s) and appends it to the chat.
        Counted by the strict LLM rate limit.

    POST /sessions/{session_id}/quiz/{message_id}/answer
        {"question_index": 0, "answer": [2]}
        -> {"question_index", "result": {...answered question...}, "quiz": {...}}
        Checked on the server; a question can be answered once.

The quiz itself comes back with GET /sessions/{id}/messages like every other
message (content_type "quiz", data in "quiz").
"""

from fastapi import APIRouter, Depends, HTTPException

from chatbot.quiz.service import QuizError, QuizService
from chatbot.routers.message_router import _require_course_access
from chatbot.schemas import CreateQuizRequest, QuizAnswerRequest
from chatbot.services.message_service import MessageService
from chatbot.services.session_service import SessionService
from dependencies import (
    get_auth_context,
    get_current_user_id,
    get_message_service,
    get_quiz_service,
    get_session_service,
)
from middleware.auth import AuthContext

router = APIRouter(prefix="/sessions", tags=["quiz"])


def _http_error(e: QuizError) -> HTTPException:
    # detail as {"code", "message"}: Moodle/JS can show a fitting text per code.
    return HTTPException(status_code=e.status, detail={"code": e.code, "message": str(e)})


@router.post("/{session_id}/quiz")
async def create_quiz(
    session_id: str,
    request: CreateQuizRequest,
    user_id: int = Depends(get_current_user_id),
    auth: AuthContext = Depends(get_auth_context),
    session_service: SessionService = Depends(get_session_service),
    quiz_service: QuizService = Depends(get_quiz_service),
    message_service: MessageService = Depends(get_message_service),
):
    session = await session_service.get_session(session_id)
    if session.user_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    _require_course_access(session, auth)

    try:
        created = await quiz_service.create_quiz(
            session_id=session_id,
            scope=request.scope,
            count=request.count,
            topic=request.topic,
            language=request.language,
        )
    except QuizError as e:
        raise _http_error(e)

    return {
        "request": message_service._to_response(created["request"], ""),
        "quiz": message_service._to_response(created["quiz"], ""),
        "title": created["title"],
    }


@router.post("/{session_id}/quiz/{message_id}/answer")
async def answer_quiz_question(
    session_id: str,
    message_id: int,
    request: QuizAnswerRequest,
    user_id: int = Depends(get_current_user_id),
    session_service: SessionService = Depends(get_session_service),
    quiz_service: QuizService = Depends(get_quiz_service),
):
    session = await session_service.get_session(session_id)
    if session.user_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        return quiz_service.answer(session_id, message_id, request.question_index, request.answer)
    except QuizError as e:
        raise _http_error(e)
