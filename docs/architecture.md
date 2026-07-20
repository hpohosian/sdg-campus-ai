# Architecture

## Overview

SDG Campus AI is a two-tier system: a **Moodle plugin** (the only thing users see) and a
standalone **Python/FastAPI backend** (all AI logic, all persistence of chat data). They
communicate over plain HTTP, secured with HMAC request signing. The FastAPI backend is
the only part of the system that talks to the LLM provider (Mistral) and to the vector
database (ChromaDB); the Moodle plugin never calls Mistral or ChromaDB directly.

The backend also reads (but never writes) Moodle's own MySQL database directly, to pull
course content for indexing and to resolve things like a user's enrolled courses or a
course's display name — this avoids having to reimplement course/enrollment logic that
Moodle already owns.

```
┌─────────────────────────────── Moodle ────────────────────────────────┐
│                                                                       │
│  Any Moodle page                                                      │
│    └─ local_ai_system_before_footer() injects a floating "AI" button  │
│         └─ opens an <iframe src="local/ai_system/index.php">          │
│                                                                       │
│  local/ai_system/index.php (server-rendered shell + Mustache template)│
│    └─ amd/src/chatbot.js (compiled to amd/build/chatbot.min.js)       │
│         ├─ Moodle external API (AJAX) for everything except streaming │
│         │    local_ai_system_get_sessions / create_session /          │
│         │    update_session / delete_session / archive_session /      │
│         │    dearchive_session / get_messages / save_partial_message  │
│         │         └─ classes/external/chatbot_api.php                 │
│         │              └─ classes/chatbot/service.php                 │
│         │                   └─ classes/external/api_client.php        │
│         │                        (HMAC-signs every request)           │
│         │                                                             │
│         └─ ajax/stream.php — plain PHP endpoint, cURL passthrough to  │
│              the FastAPI streaming endpoint (SSE), bypasses the       │
│              external API layer because Moodle's AJAX framework       │
│              doesn't support streaming responses                      │
│                                                                       │
│  classes/observer.php — listens for course_created / course_updated / │
│    course_module_* / course_section_updated Moodle events, queues an  │
│    adhoc reindex task (deduplicated) for the affected course          │
│  classes/task/reindex_course_task.php — runs on Moodle's cron,        │
│    calls POST /rag/index/{course_id} on the backend                   │
│                                                                       │
└─────────────────────────────────┬─────────────────────────────────────┘
                                  │ HMAC-signed HTTPS/HTTP
                                  ▼
┌────────────────────────────── FastAPI backend (api/) ──────────────────┐
│                                                                        │
│  main.py — FastAPI app, CORS, mounts 3 routers:                        │
│    session_router  (/sessions ...)                                     │
│    message_router   (/sessions/{id}/messages ...)                      │
│    rag_router        (/rag ...)                                        │
│                                                                        │
│  chatbot/                                                              │
│    routers/     → thin HTTP layer, auth via X-User-Id header           │
│    services/     → business logic (SessionService, MessageService,     │
│                     AIService, RagService)                             │
│    repositories/ → persistence for the plugin's own tables             │
│                     (sessions, messages, message translations, RAG)    │
│    prompts.py    → all system prompts (RAG-grounded tutor, plain       │
│                     tutor, title generation)                           │
│    course_links.py → builds safe, ready-made markdown links to         │
│                       courses so the LLM never invents a URL           │
│                                                                        │
│  rag/                                                                  │
│    loaders/  → pulls raw content out of Moodle's own DB + filesystem   │
│                (pages, book chapters, labels, section summaries, PDFs) │
│    chunker.py    → paragraph/sentence-aware text splitter              │
│    embeddings.py → sentence-transformers wrapper                       │
│    vector_store.py → ChromaDB wrapper (one collection per course)      │
│    retriever.py  → similarity search + prompt-context formatting,      │
│                     single-course or cross-course (enrolled) modes     │
│    ingestion.py  → chunk → embed → store pipeline                      │
│                                                                        │
│  llm/                                                                  │
│    base.py    → BaseLLM abstract interface (chat / stream)             │
│    mistral.py → Mistral implementation of BaseLLM                      │
│                                                                        │
│  translation/translator.py → LLM-backed message translator             │
│                                                                        │
│  db/                                                                   │
│    models/       → SQLAlchemy ORM models for the plugin's own tables   │
│    repositories/  → read-only access to native Moodle tables           │
│                      (mdl_course, mdl_user_enrolments, mdl_enrol)      │
│    connection.py → SQLAlchemy engine/session against DATABASE_URL      │
│                     (this is literally Moodle's MySQL database)        │
│                                                                        │
│  middleware/                                                           │
│    auth.py          → HMACAuthMiddleware (verifies plugin→API calls)   │
│    internal_auth.py → verify_internal_api_key (for /rag/index*)        │
│                                                                        │
│  settings.py / dependencies.py → pydantic-settings config + FastAPI    │
│                                    dependency-injection wiring         │
│                                                                        │
└─────────────────────────────────┬──────────────────────────────────────┘
                                  │
                    ┌─────────────┴──────────────┐
                    ▼                            ▼
           MySQL (Moodle's DB)           ChromaDB (local, persisted
           - plugin's own 4 tables         to data/chromadb/)
           - read-only access to           - one collection per course:
             Moodle's own tables             "course_{id}"
                    │
                    ▼
           Mistral API (LLM)
```

## System components

### 1. Moodle plugin (`moodle-plugin/local/ai_system`)

A standard Moodle "local" plugin. It is responsible only for **UI and transport** — it
holds no AI logic and stores no chat content of its own (all chat data lives in the
FastAPI backend's database, which happens to be the same MySQL instance as Moodle's).

Its jobs:
- Inject the floating chat button/panel into every relevant Moodle page.
- Render the chat UI (sidebar, message list, course/language pickers) server-side via a
  Mustache template, then hand off to a JavaScript module for all interactivity.
- Forward every user action to the FastAPI backend, signing each request with HMAC so the
  backend can trust it came from this Moodle instance.
- React to Moodle course-content-changed events by queuing a background reindex task.

### 2. FastAPI backend (`api/`)

Owns all AI behavior and all chat persistence. Structured in a fairly conventional
layered style:

```
router → service → repository → SQLAlchemy model / external system (ChromaDB, Mistral)
```

- **Routers** parse/validate HTTP input (Pydantic schemas) and enforce per-request
  identity (`X-User-Id` header) and ownership checks (a user can only read/modify their
  own sessions).
- **Services** hold the actual business logic — deciding what context to retrieve,
  building prompts, orchestrating streaming, deciding when to auto-generate a title,
  when to use cached translations, etc.
- **Repositories** are thin persistence wrappers around SQLAlchemy (for the plugin's own
  tables) or around ChromaDB (for the RAG repository).

### 3. RAG subsystem (`api/rag`)

A self-contained pipeline that can ingest Moodle course content into a per-course
ChromaDB collection, and retrieve relevant chunks for a query at chat time. See
[docs/backend/rag.md](backend/rag.md) for full detail.

### 4. LLM layer (`api/llm`)

A tiny abstraction (`BaseLLM`) with one concrete implementation (`MistralLLM`), used both
for chat generation and (via the same interface) for translation and title generation.
Swapping providers means adding a new `BaseLLM` subclass — nothing else in the codebase
needs to change.

## Data storage

There is **no separate database** for the AI system — the FastAPI backend connects to
the **same MySQL database as Moodle** (`DATABASE_URL` in `.env`) and adds four of its own
tables (all prefixed to match Moodle's own naming convention):

| Table | Purpose |
|---|---|
| `mdl_local_ai_system_sessions` | one row per chat session |
| `mdl_local_ai_system_messages` | one row per chat message (user or assistant) |
| `mdl_local_ai_system_message_translations` | cached per-language translations of messages |
| `mdl_local_ai_system_logs` | defined in the plugin's `install.xml` for future use; not currently written to by any code path |

The backend also **reads** (never writes) native Moodle tables directly via raw SQL:
`mdl_course`, `mdl_user_enrolments`, `mdl_enrol`, `mdl_course_sections`, `mdl_page`,
`mdl_book`, `mdl_book_chapters`, `mdl_label`, `mdl_files`, `mdl_context`,
`mdl_course_modules`, `mdl_modules`. See
[docs/backend/database.md](backend/database.md) for the full schema and query details.

Vector embeddings live in **ChromaDB**, persisted to disk under `data/chromadb/` (a
`PersistentClient`, not a server — no separate DB process to run). One collection per
course, named `course_{course_id}`.

## Security model

Two independent layers of protection:

1. **HMAC request signing** (`middleware/auth.py`, `HMACAuthMiddleware`) — every request
   from the plugin includes `X-Timestamp` and `X-Signature` headers; the signature is
   `HMAC-SHA256(secret, timestamp + body)` using a shared secret (`MOODLE_SECRET` /
   plugin setting `api_secret`). Requests older than 5 minutes are rejected (replay
   protection). **Note:** this middleware exists in the codebase but is *not* currently
   registered in `main.py` (`app.add_middleware(...)` is not called for it) — see
   [docs/backend/overview.md](backend/overview.md) for the implication.
2. **Internal API key** (`middleware/internal_auth.py`) — a second, separate shared
   secret (`INTERNAL_API_KEY` / plugin setting `internal_api_key`) required specifically
   on the `/rag/index/{course_id}` and `/rag/index-all` endpoints, since these are only
   ever meant to be called by the scheduled reindex task, not by a logged-in user's
   browser session.

**User identity** itself is currently passed via a plain `X-User-Id` header
(`dependencies.get_current_user_id`), explicitly documented in code as a temporary
development mechanism, to be replaced later with real Moodle token validation.

## Course-scoped retrieval & enrollment safety

A chat session can be tied to a specific course (`course_id` set at creation) or left
"global." The scope determines retrieval:

- **Course-scoped session** → only that course's ChromaDB collection is searched.
- **Global session** → the backend looks up the user's *actively enrolled* courses
  (`CourseRepository.get_enrolled_course_ids`, reading Moodle's own enrolment tables) and
  searches across all of their collections, merging and re-ranking results. This is a
  deliberate safety boundary: a user can never receive retrieved context from a course
  they are not enrolled in, because the enrolled-course-id list is looked up server-side
  from Moodle's own data, not trusted from client input.

## Internationalization

Two independent i18n concerns exist in the system:

- **Moodle UI strings** — standard Moodle `lang/en/local_ai_system.php` string file
  (labels, buttons, tooltips). English only right now; no other `lang/xx` folders exist.
- **Chat content translation** — a completely separate feature: an already-generated
  conversation can be *displayed* in English/German/Russian/Ukrainian on demand, using
  the LLM as a translation engine (`translation/translator.py`), with results cached per
  `(message_id, language)` pair in `mdl_local_ai_system_message_translations` so the same
  message is never translated twice. This is unrelated to which language the assistant
  answers in originally (which follows whatever language the student writes in, since no
  language is forced in the system prompt).
