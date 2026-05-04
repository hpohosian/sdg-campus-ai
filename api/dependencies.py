from functools import lru_cache
from fastapi import Depends
from sqlalchemy.orm import Session as DBSession

from llm.base import BaseLLM
from llm.mistral import MistralLLM
from settings import Settings

from db.connection import get_db

from chatbot.services.session_service import SessionService
from chatbot.repositories.session_repository import SessionRepository


@lru_cache
def get_settings() -> Settings:
    return Settings()


def get_llm(settings: Settings = Depends(get_settings)) -> BaseLLM:
    return MistralLLM(api_key=settings.MISTRAL_API_KEY)


def get_session_repository(db: DBSession = Depends(get_db)) -> SessionRepository:
    return SessionRepository(db)


def get_session_service(
    repo: SessionRepository = Depends(get_session_repository),
):
    return SessionService(repo)

