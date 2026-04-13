from functools import lru_cache
from fastapi import Depends

from llm.base import BaseLLM
from llm.mistral import MistralLLM
from settings import Settings
from chatbot.service import ChatService
from chatbot.session_repository import SessionRepository


@lru_cache
def get_settings() -> Settings:
    return Settings()

@lru_cache
def get_session_repository() -> SessionRepository:
    return SessionRepository()

def get_llm(settings: Settings = Depends(get_settings)) -> BaseLLM:
    return MistralLLM(api_key=settings.MISTRAL_API_KEY)

def get_chat_service(
    llm: BaseLLM = Depends(get_llm),
    session_repo: SessionRepository = Depends(get_session_repository)
) -> ChatService:
    return ChatService(
        llm=llm,
        session_repo=session_repo
    )
