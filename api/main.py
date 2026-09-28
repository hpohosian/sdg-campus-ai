import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from chatbot.routers.session_router import router as session_router
from chatbot.routers.message_router import router as message_router
from chatbot.routers.rag_router import router as rag_router
from middleware.timing import TimingMiddleware
from dependencies import get_embedding_model, get_vector_store, get_llm


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Warm-up at server start: load heavy objects once, so the first user
    request doesn't pay for them.
    """
    start = time.perf_counter()

    model = get_embedding_model()
    # IMPORTANT: keyword argument, exactly like FastAPI calls it.
    # lru_cache treats f(x) and f(embedding_model=x) as different cache keys.
    get_vector_store(embedding_model=model)
    model.embed_text("warm-up")

    get_llm()

    print(f"[startup] embedding model + vector store + LLM client ready in "
          f"{time.perf_counter() - start:.1f} s")
    yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(TimingMiddleware)

origins = [
    "http://127.0.0.1",  # Moodle address
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # allow these domains
    allow_credentials=True,
    allow_methods=["*"],    # GET, POST, PUT, DELETE...
    allow_headers=["*"],    # any headers
)

app.include_router(session_router)
app.include_router(message_router)
app.include_router(rag_router)
