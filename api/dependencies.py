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
from rag.embeddings import EmbeddingModel
from rag.vector_store import VectorStore
from rag.retriever import Retriever

@lru_cache
def get_settings() -> Settings:
    return Settings()


def get_llm(settings: Settings = Depends(get_settings)) -> BaseLLM:
    return MistralLLM(api_key=settings.MISTRAL_API_KEY)


@lru_cache
def get_embedding_model() -> EmbeddingModel:
    return EmbeddingModel()


@lru_cache
def get_vector_store(
    embedding_model: EmbeddingModel = Depends(get_embedding_model),
) -> VectorStore:
    return VectorStore(embedding_model=embedding_model)


def get_retriever(
    vector_store: VectorStore = Depends(get_vector_store),
) -> Retriever:
    return Retriever(vector_store=vector_store)


def get_ai_service(
    llm: BaseLLM = Depends(get_llm),
    retriever: Retriever = Depends(get_retriever),
):
    return AIService(llm=llm, retriever=retriever)


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
    ai_service: AIService = Depends(get_ai_service),
):
    return MessageService(message_repo, session_repo, ai_service)


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

    if not x_user_id or x_user_id == "0":
        raise HTTPException(status_code=401, detail="Missing user header")

    try:
        return int(x_user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user id")
