from fastapi import APIRouter, Depends

from chatbot.schemas import ChatRequest, ChatResponse
from chatbot.service import ChatService
from dependencies import get_chat_service

import logging

logger = logging.getLogger("ai")


router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    service: ChatService = Depends(get_chat_service), 
):
    response = await service.handle_message(request)
    return response
