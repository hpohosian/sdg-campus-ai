from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from chatbot.schemas import MessageResponse, SendMessageRequest

from chatbot.services.message_service import MessageService
from chatbot.services.session_service import SessionService
# from chatbot.services.ai_service import AIService

from chatbot.schemas import SendMessageRequest

from dependencies import (
    get_message_service,
    get_session_service,
    get_current_user_id,
    # get_ai_service,
)


router = APIRouter(prefix="/sessions", tags=["messages"])


# =========================
# GET SESSION MESSAGES
# =========================
@router.get("/{session_id}/messages", response_model=list[MessageResponse])
async def get_session_messages(
    session_id: str,
    user_id: int = Depends(get_current_user_id),

    session_service: SessionService = Depends(get_session_service),

    message_service: MessageService = Depends(get_message_service),
):
    session = await session_service.get_session(session_id)

    if session.user_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    messages = await message_service.get_session_messages(session_id)

    return messages


# =========================
# CREATE USER MESSAGE AND AI RESPONSE
# =========================
@router.post("/{session_id}/messages")
async def send_message(
    session_id: str,
    request: SendMessageRequest,
    user_id: int = Depends(get_current_user_id),
    session_service: SessionService = Depends(get_session_service),
    message_service: MessageService = Depends(get_message_service),
):
    session = await session_service.get_session(session_id)

    if session.user_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    result = await message_service.chat(
        session_id=session_id,
        content=request.content
    )

    return result


# =========================
# STREAM AI RESPONSE
# =========================
@router.post("/{session_id}/messages/stream")
async def stream_message(
    session_id: str,
    request: SendMessageRequest,
    user_id: int = Depends(get_current_user_id),
    session_service: SessionService = Depends(get_session_service),
    message_service: MessageService = Depends(get_message_service),
):
    session = await session_service.get_session(session_id)

    if session.user_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    async def generator():
        full = ""

        async for token in message_service.chat_stream(session_id, request.content):
            full += token
            yield f"data: {token}\n\n"

    return StreamingResponse(generator(), media_type="text/event-stream")
