from functools import lru_cache
from fastapi import Depends

from api.llm.base import BaseLLM
from api.llm.mistral import MistralLLM
from api.settings import Settings
from api.chatbot.service import ChatService


@lru_cache
def get_settings() -> Settings:
    return Settings()

def get_llm(settings: Settings = Depends(get_settings)) -> BaseLLM:
    return MistralLLM(api_key=settings.MISTRAL_API_KEY)

def get_chat_service(llm: BaseLLM = Depends(get_llm)) -> ChatService:
    return ChatService(llm=llm)
