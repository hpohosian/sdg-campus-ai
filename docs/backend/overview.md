# Backend Overview

## Project layout

```
api/
├── main.py                 FastAPI app entrypoint, CORS, router mounting
├── settings.py             pydantic-settings config, loaded from .env
├── dependencies.py         FastAPI dependency-injection wiring (get_* functions)
│
├── chatbot/
│   ├── routers/
│   │   ├── session_router.py    /sessions ...
│   │   ├── message_router.py    /sessions/{id}/messages ...
│   │   └── rag_router.py        /rag ...
│   ├── services/
│   │   ├── session_service.py
│   │   ├── message_service.py
│   │   ├── ai_service.py        prompt building, calls the LLM
│   │   └── rag_service.py       background indexing orchestration
│   ├── repositories/
│   │   ├── session_repository.py
│   │   ├── message_repository.py
│   │   ├── message_translation_repository.py
│   │   └── rag_repository.py    thin wrapper over VectorStore
│   ├── prompts.py           all LLM system prompts
│   ├── course_links.py      builds safe markdown links to courses
│   └── schemas.py           Pydantic request/response models
│
├── rag/
│   ├── loaders/
│   │   ├── moodle_db_loader.py  pulls text content from Moodle's DB
│   │   ├── pdf_loader.py        pulls + extracts text from Moodle PDF uploads
│   │   └── course_indexer.py    orchestrates both loaders + ingestion
│   ├── chunker.py           paragraph/sentence-aware text splitter
│   ├── embeddings.py        sentence-transformers wrapper
│   ├── vector_store.py      ChromaDB wrapper
│   ├── retriever.py         similarity search + context formatting
│   └── ingestion.py         chunk → embed → store pipeline
│
├── llm/
│   ├── base.py              BaseLLM abstract interface
│   └── mistral.py           Mistral implementation
│
├── translation/
│   └── translator.py        LLM-backed message translation
│
├── db/
│   ├── connection.py        SQLAlchemy engine/session (points at Moodle's MySQL)
│   ├── models/               ORM models for the plugin's own 3 tables in use
│   │   ├── session.py
│   │   ├── message.py
│   │   └── message_translation.py
│   └── repositories/
│       ├── db_course_repository.py     read-only access to native mdl_course* tables
│       └── db_session_repository.py    LEGACY / unused — see note below
│
└── middleware/
    ├── auth.py               HMACAuthMiddleware (see note below — not currently mounted)
    └── internal_auth.py      verify_internal_api_key dependency
```

> **Legacy/dead code note:** `db/repositories/db_session_repository.py` (`DbSessionRepository`)
> is not imported or used anywhere — the actual session persistence goes through
> `chatbot/repositories/session_repository.py` (`SessionRepository`) instead. It also has
> a broken import (`from datetime import int`, which is not valid Python) and would fail
> if it were ever imported. Safe to delete, or worth cleaning up before it confuses a
> future contributor.

## Configuration (`settings.py` / `.env`)

Settings are loaded via `pydantic-settings` from a `.env` file in `api/`. All fields:

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `MISTRAL_API_KEY` | yes | — | Mistral API key |
| `MISTRAL_MODEL` | no | `mistral-medium` | Mistral model name (e.g. `mistral-large-latest`) |
| `MOODLE_SECRET` | yes | — | HMAC shared secret for `HMACAuthMiddleware` |
| `LOG_LEVEL` | no | `INFO` | not currently wired to a logging config, reserved |
| `ENVIRONMENT` | no | `development` | reserved, not currently branched on |
| `DEBUG` | no | `False` | reserved, not currently branched on |
| `DATABASE_URL` | yes | — | SQLAlchemy URL, points at Moodle's MySQL DB (e.g. `mysql+pymysql://user:pass@host:port/moodle`) |
| `MOODLEDATA_PATH` | no | Windows dev path | filesystem path to Moodle's `moodledata` directory, used to locate PDF files on disk for text extraction |
| `MOODLE_BASE_URL` | no | `http://127.0.0.1` | used to build clickable links back into Moodle (course links, PDF `pluginfile.php` links) — **no trailing slash** |
| `INTERNAL_API_KEY` | yes | — | shared secret required on `/rag/index*` endpoints |
| `EMBEDDING_MODEL` | no | `paraphrase-multilingual-mpnet-base-v2` | HuggingFace sentence-transformers model name |
| `HF_HOME` | no | Windows dev path | HuggingFace cache directory |
| `HF_HUB_DISABLE_XET` | no | `"1"` | disables the newer Xet download backend for HF Hub |

Note that `MOODLEDATA_PATH` and `HF_HOME` currently default to Windows-style paths
(`D:\...`) hard-coded in `settings.py` — these **must** be overridden in `.env` on any
non-Windows deployment, which the provided `.env` already does correctly.

## Dependency injection (`dependencies.py`)

FastAPI's `Depends()` system is used throughout; the chain for a typical request looks
like:

```
get_settings()  (lru_cache — one Settings instance for the app's lifetime)
   ├─ get_llm()                 → MistralLLM(api_key=...)
   ├─ get_embedding_model()     (lru_cache — loads the sentence-transformers model ONCE)
   │    └─ get_vector_store()   (lru_cache — one ChromaDB PersistentClient)
   │         └─ get_retriever()
   │              └─ get_ai_service(llm, retriever)
   ├─ get_translator(llm)
   ├─ get_db()                  (per-request SQLAlchemy session, closed after the request)
   │    ├─ get_session_repository(db)   → get_session_service(repo)
   │    ├─ get_message_repository(db)
   │    ├─ get_message_translation_repository(db)
   │    └─ get_course_repository(db)
   └─ get_message_service(message_repo, session_repo, ai_service, course_repo,
                           translation_repo, translator)
```

The `@lru_cache` on `get_embedding_model`/`get_vector_store`/`get_settings` matters
operationally: the sentence-transformers model (hundreds of MB) and the ChromaDB client
are loaded exactly once per process, not once per request — the first request after
server startup will be noticeably slower while the embedding model loads
(`EmbeddingModel.__init__` prints `Loading embedding model: ...` / `Embedding model
loaded.` to stdout).

`get_current_user_id` (used by every session/message route) reads an `X-User-Id` header
and raises `401` if missing/`"0"`, or `400` if not a valid integer. The docstring in the
code is explicit that this is a **temporary development mechanism** — production is
intended to validate a real Moodle token instead, but that has not been implemented yet.

## Running the API

There is no committed `requirements.txt`/`pyproject.toml` in the repository. The
following were inferred from the checked-in virtual environment
(`api/.venv/Lib/site-packages`) and represent the actual dependency set the project runs
against — a `requirements.txt` should be generated and committed so the environment is
reproducible without shipping a `.venv`:

**Core**
```
fastapi
uvicorn[standard]
pydantic
pydantic-settings
python-dotenv
sqlalchemy
pymysql
```

**LLM**
```
mistralai
```

**RAG**
```
chromadb
sentence-transformers
torch
transformers
tokenizers
huggingface-hub
scikit-learn
numpy
pymupdf          # imported as `fitz`
beautifulsoup4
```

Local dev run (from the `api/` directory, with `.venv` activated):

```bash
uvicorn main:app --reload --port 8001
```

Port `8001` is what the Moodle plugin's default `api_base_url` setting
(`http://127.0.0.1:8001`) and `ajax/stream.php`'s hard-coded `$base_url` both expect —
keep them in sync if this changes.

> **Note on `ajax/stream.php`:** its FastAPI base URL (`http://127.0.0.1:8001`) is
> currently hard-coded in the PHP file itself rather than read from the plugin's
> `api_base_url` admin setting the way `api_client.php` does. If the backend's address
> changes, this file needs to be updated separately from the plugin settings page.

## Import path duality (`try/except ModuleNotFoundError`)

Several modules (`course_links.py`, `embeddings.py`, `pdf_loader.py`,
`db/repositories/db_session_repository.py`) contain a pattern like:

```python
try:
    from api.settings import settings
except ModuleNotFoundError:
    from settings import settings
```

This exists because the codebase is run with `api/` itself as the working directory /
import root (`from settings import settings` — matches how `uvicorn main:app` is run from
inside `api/`), but some tooling or test setup apparently imports it as the `api` package
from the repository root (`from api.settings import settings`). Worth standardizing on
one import root going forward (e.g. always running from repo root with
`uvicorn api.main:app`) to remove the need for this fallback pattern everywhere it
appears.

## CORS

`main.py` only allows the origin `http://127.0.0.1` (Moodle's dev address). Any other
origin will be rejected by the browser for cross-origin requests. Update the `origins`
list in `main.py` for staging/production Moodle URLs.
