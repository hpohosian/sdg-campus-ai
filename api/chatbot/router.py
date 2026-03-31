from fastapi import APIRouter
from fastapi import APIRouter
from chatbot.schemas import ChatRequest, ChatResponse
from chatbot.service import ChatService

router = APIRouter()

chat_service = ChatService()


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    response = chat_service.generate_response(request.message)

    return ChatResponse(response=response)