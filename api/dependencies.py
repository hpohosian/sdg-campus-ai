from functools import lru_cache
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session as DBSession

from llm.base import BaseLLM
from llm.mistral import MistralLLM
from settings import Settings

from db.connection import get_db, get_moodle_db
from middleware.auth import AuthContext

from chatbot.services.session_service import SessionService
from chatbot.repositories.session_repository import SessionRepository

from chatbot.services.message_service import MessageService
from chatbot.repositories.message_repository import MessageRepository
from chatbot.repositories.message_translation_repository import MessageTranslationRepository

from db.repositories.db_course_repository import CourseRepository

from chatbot.services.ai_service import AIService
from translation.translator import Translator
from rag.embeddings import EmbeddingModel
from rag.vector_store import VectorStore
from rag.retriever import Retriever

from chatbot.services.image_storage import ImageStorage


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_llm() -> BaseLLM:
    """
    Created ONCE per process. Building the Mistral client costs ~500 ms
    (HTTP clients + SSL context), so it must not happen per request.
    """
    settings = get_settings()
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


def get_translator(
    llm: BaseLLM = Depends(get_llm),
) -> Translator:
    return Translator(llm=llm)


def get_session_repository(db: DBSession = Depends(get_db)) -> SessionRepository:
    return SessionRepository(db)


def get_message_repository(db: DBSession = Depends(get_db)) -> MessageRepository:
    return MessageRepository(db)


def get_image_storage() -> ImageStorage:
    return ImageStorage()


def get_session_service(
    repo: SessionRepository = Depends(get_session_repository),
    message_repo: MessageRepository = Depends(get_message_repository),
    image_storage: ImageStorage = Depends(get_image_storage),
):
    return SessionService(repo, message_repo, image_storage)


def get_message_translation_repository(
    db: DBSession = Depends(get_db),
) -> MessageTranslationRepository:
    return MessageTranslationRepository(db)


def get_auth_context(request: Request) -> AuthContext:
    """
    The verified identity of the caller (user id + the courses the user is
    enrolled in), as signed by the Moodle plugin. It is put on the request by
    HMACAuthMiddleware after the signature has been checked; it is the ONLY
    trusted source of "who is asking" -- never read it from a plain header.
    """
    auth = getattr(request.state, "auth", None)
    if auth is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return auth


def get_current_user_id(auth: AuthContext = Depends(get_auth_context)) -> int:
    if auth.user_id <= 0:
        raise HTTPException(status_code=401, detail="Missing user")
    return auth.user_id


def get_course_repository(db: DBSession = Depends(get_moodle_db)) -> CourseRepository:
    return CourseRepository(db)


def get_message_service(
    message_repo: MessageRepository = Depends(get_message_repository),
    session_repo: SessionRepository = Depends(get_session_repository),
    ai_service: AIService = Depends(get_ai_service),
    auth: AuthContext = Depends(get_auth_context),
    translation_repo: MessageTranslationRepository = Depends(get_message_translation_repository),
    translator: Translator = Depends(get_translator),
    image_storage: ImageStorage = Depends(get_image_storage),
):
    return MessageService(
        message_repo,
        session_repo,
        ai_service,
        auth.enrolled_courses,
        translation_repo,
        translator,
        image_storage,
    )
