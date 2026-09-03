from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
import json
import os
import mimetypes

from chatbot.schemas import MessageResponse, SendMessageRequest, EditMessageRequest

from chatbot.services.message_service import MessageService
from chatbot.services.session_service import SessionService

from dependencies import (
    get_message_service,
    get_session_service,
    get_current_user_id,
)


router = APIRouter(prefix="/sessions", tags=["messages"])

# ~8 MB of raw image bytes -> base64 inflates size by ~4/3, so cap the
# encoded string a bit above that. Mirrors the limit enforced in stream.php
# on the Moodle side; this is the backend's own belt-and-braces check.
MAX_IMAGE_BASE64_CHARS = 11 * 1024 * 1024


def _validate_image_size(request: SendMessageRequest) -> None:
    if request.image_base64 and len(request.image_base64) > MAX_IMAGE_BASE64_CHARS:
        raise HTTPException(status_code=413, detail="Image too large")


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

    messages = await message_service.get_session_messages_for_display(session_id)  # CHANGED

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

    _validate_image_size(request)

    result = await message_service.chat(
        session_id=session_id,
        content=request.content,
        image_base64=request.image_base64,
        image_mime_type=request.image_mime_type,
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

    _validate_image_size(request)

    result: dict = {}

    async def generator():
        async for token in message_service.chat_stream(
            session_id,
            request.content,
            image_base64=request.image_base64,
            image_mime_type=request.image_mime_type,
            result=result,
        ):
            payload = json.dumps({"token": token})
            yield f"data: {payload}\n\n"

        updated_session = await session_service.get_session(session_id)
        title_payload = json.dumps({"title": updated_session.title})
        yield f"data: {title_payload}\n\n"

        yield f"data: {json.dumps({'meta': result})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generator(), media_type="text/event-stream")


# =========================
# EDIT A USER MESSAGE (new version + fresh streamed reply)
# =========================
@router.post("/{session_id}/messages/{message_id}/edit/stream")
async def edit_message_stream(
    session_id: str,
    message_id: int,
    request: EditMessageRequest,
    user_id: int = Depends(get_current_user_id),
    session_service: SessionService = Depends(get_session_service),
    message_service: MessageService = Depends(get_message_service),
):
    session = await session_service.get_session(session_id)

    if session.user_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    result: dict = {}

    async def generator():
        try:
            async for token in message_service.edit_message_stream(
                session_id, message_id, request.content, result=result
            ):
                yield f"data: {json.dumps({'token': token})}\n\n"
        except ValueError as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            yield "data: [DONE]\n\n"
            return

        yield f"data: {json.dumps({'meta': result})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generator(), media_type="text/event-stream")


# =========================
# REGENERATE AN ASSISTANT REPLY (new version, streamed)
# =========================
@router.post("/{session_id}/messages/{message_id}/regenerate/stream")
async def regenerate_message_stream(
    session_id: str,
    message_id: int,
    user_id: int = Depends(get_current_user_id),
    session_service: SessionService = Depends(get_session_service),
    message_service: MessageService = Depends(get_message_service),
):
    session = await session_service.get_session(session_id)

    if session.user_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    result: dict = {}

    async def generator():
        try:
            async for token in message_service.regenerate_message_stream(
                session_id, message_id, result=result
            ):
                yield f"data: {json.dumps({'token': token})}\n\n"
        except ValueError as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            yield "data: [DONE]\n\n"
            return

        yield f"data: {json.dumps({'meta': result})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generator(), media_type="text/event-stream")


# =========================
# VERSION METADATA FOR THE WHOLE SESSION
# =========================
@router.post("/{session_id}/messages-versions-meta")
async def get_versions_meta(
    session_id: str,
    user_id: int = Depends(get_current_user_id),
    session_service: SessionService = Depends(get_session_service),
    message_service: MessageService = Depends(get_message_service),
):
    session = await session_service.get_session(session_id)

    if session.user_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    return await message_service.get_session_versions_meta(session_id)


# =========================
# ACTIVATE A SPECIFIC VERSION
# =========================
@router.post("/{session_id}/messages/{message_id}/activate")
async def activate_message_version(
    session_id: str,
    message_id: int,
    user_id: int = Depends(get_current_user_id),
    session_service: SessionService = Depends(get_session_service),
    message_service: MessageService = Depends(get_message_service),
):
    session = await session_service.get_session(session_id)

    if session.user_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        await message_service.activate_message_version(session_id, message_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return {"success": True}


@router.post("/{session_id}/messages/partial", response_model=MessageResponse)
async def save_partial_message(
    session_id: str,
    request: SendMessageRequest,
    user_id: int = Depends(get_current_user_id),
    session_service: SessionService = Depends(get_session_service),
    message_service: MessageService = Depends(get_message_service),
):
    session = await session_service.get_session(session_id)

    if session.user_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        message = await message_service.create_partial_assistant_message(session_id, request.content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return MessageResponse.from_orm(message)


# =========================
# SERVE A MESSAGE'S ATTACHED IMAGE
# =========================
# POST (not GET) so the existing HMAC-over-JSON-body signature scheme
# (see stream.php / dependencies.get_current_user_id) applies unchanged —
# the request body itself isn't used for anything here.
@router.post("/{session_id}/messages/{message_id}/image")
async def get_message_image(
    session_id: str,
    message_id: int,
    request: SendMessageRequest,
    user_id: int = Depends(get_current_user_id),
    session_service: SessionService = Depends(get_session_service),
    message_service: MessageService = Depends(get_message_service),
):
    session = await session_service.get_session(session_id)

    if session.user_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    abs_path = message_service.get_image_abs_path(session_id, message_id)

    if not abs_path or not os.path.isfile(abs_path):
        raise HTTPException(status_code=404, detail="Image not found")

    media_type = mimetypes.guess_type(abs_path)[0] or "application/octet-stream"
    return FileResponse(abs_path, media_type=media_type)
