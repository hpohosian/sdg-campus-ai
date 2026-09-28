import time
from sqlalchemy import text

from settings import Settings
from llm.mistral import MistralLLM
from translation.translator import Translator
from rag.retriever import Retriever
from chatbot.services.ai_service import AIService
from chatbot.services.image_storage import ImageStorage
from chatbot.repositories.message_repository import MessageRepository
from chatbot.repositories.message_translation_repository import MessageTranslationRepository
from chatbot.repositories.session_repository import SessionRepository
from db.repositories.db_course_repository import CourseRepository
from db.connection import SessionLocal
from dependencies import get_embedding_model, get_vector_store


def timed(label, fn, repeat=3):
    obj = None
    for i in range(repeat):
        t = time.perf_counter()
        obj = fn()
        print(f"{label} #{i + 1}: {(time.perf_counter() - t) * 1000:.0f} ms")
    return obj


settings = timed("Settings()", Settings)

model = timed("get_embedding_model (heavy)", get_embedding_model, repeat=1)
store = timed("get_vector_store", lambda: get_vector_store(embedding_model=model), repeat=2)

llm = timed("MistralLLM(...)", lambda: MistralLLM(api_key=settings.MISTRAL_API_KEY))
timed("Translator", lambda: Translator(llm=llm))

retriever = timed("Retriever", lambda: Retriever(vector_store=store))
timed("AIService", lambda: AIService(llm=llm, retriever=retriever))

timed("ImageStorage", ImageStorage)

db = SessionLocal()
timed("DB: SELECT 1", lambda: db.execute(text("SELECT 1")).scalar())
timed("SessionRepository", lambda: SessionRepository(db))
timed("MessageRepository", lambda: MessageRepository(db))
timed("MessageTranslationRepository", lambda: MessageTranslationRepository(db))
timed("CourseRepository", lambda: CourseRepository(db))
db.close()