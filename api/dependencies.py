from functools import lru_cache
from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session as DBSession

from llm.base import BaseLLM
from llm.mistral import MistralLLM
from settings import Settings

from db.connection import get_db

from chatbot.services.session_service import SessionService
from chatbot.repositories.session_repository import SessionRepository

from chatbot.services.message_service import MessageService
from chatbot.repositories.message_repository import MessageRepository

from chatbot.services.ai_service import AIService


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


def get_message_repository(db: DBSession = Depends(get_db)) -> MessageRepository:
    return MessageRepository(db)

def get_message_service(
    message_repo: MessageRepository = Depends(get_message_repository),
    session_repo: SessionRepository = Depends(get_session_repository),
):
    return MessageService(message_repo, session_repo)


def get_ai_service(
    llm: BaseLLM = Depends(get_llm),
):
    return AIService(llm)


def get_current_user_id(x_user_id: str | None = Header(default=None)) -> int:
    """
    Temporary auth system for development.
    In production this will be replaced with Moodle token validation.
    
    Now in Postman - add Header (X-User-Id: n)
    
    Option 2 (correct for Moodle later)
    def get_current_user_id(token: str = Header(...)):
        # 1. check Moodle token
        # 2. request in Moodle API
        # 3. return user.id
    """

    if not x_user_id:
        raise HTTPException(status_code=401, detail="Missing user header")

    try:
        return int(x_user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user id")
