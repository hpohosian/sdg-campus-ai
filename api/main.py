import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from chatbot.routers.session_router import router as session_router
from chatbot.routers.message_router import router as message_router
from chatbot.routers.rag_router import router as rag_router
from middleware.timing import TimingMiddleware
from middleware.auth import HMACAuthMiddleware
from db.connection import chat_engine
from settings import settings
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


# The interactive API docs are only available outside production.
_docs_enabled = settings.ENVIRONMENT.lower() != "production"

app = FastAPI(
    lifespan=lifespan,
    docs_url="/docs" if _docs_enabled else None,
    redoc_url="/redoc" if _docs_enabled else None,
    openapi_url="/openapi.json" if _docs_enabled else None,
)

# Paths that need no signature: the health check (used by Docker / monitoring)
# and, outside production, the API docs. EVERYTHING else must be signed by the
# Moodle plugin (see middleware/auth.py).
_unsigned_paths = {"/health"}
if _docs_enabled:
    _unsigned_paths |= {"/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"}

# Added first = innermost: Timing and CORS still wrap it, so rejected
# requests are timed/logged like any other.
app.add_middleware(
    HMACAuthMiddleware,
    secret=settings.MOODLE_SECRET,
    exempt_paths=frozenset(_unsigned_paths),
)

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


@app.get("/health")
def health():
    """Liveness + readiness: the process is up and the chat database answers."""
    try:
        with chat_engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        raise HTTPException(status_code=503, detail="database unavailable")
    return {"status": "ok"}
