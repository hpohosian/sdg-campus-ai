# SDG Campus AI

AI-powered chatbot module for the **SDG Campus** platform, built on top of **Moodle**.

This repository contains two cooperating parts:

- **`api/`** — a Python/FastAPI backend that owns all AI logic: chat, Retrieval-Augmented
  Generation (RAG) over course materials, multilingual translation of chat history, and
  session/message persistence.
- **`moodle-plugin/`** — a Moodle local plugin (`local_ai_system`) written in PHP that
  embeds a floating chat widget into every Moodle page and talks to the FastAPI backend
  over signed HTTP requests.

> This README reflects the state of the project as of **July 2026**. It replaces the
> earlier prototype-stage README — RAG, translation, streaming, session management
> (archive/pin/rename), and the course-picker are all implemented and working.

---

## 📚 Documentation map

| Doc | Contents |
|---|---|
| [docs/architecture.md](docs/architecture.md) | System components, tech stack, how the pieces fit together |
| [docs/data-flow.md](docs/data-flow.md) | Step-by-step walkthroughs of every major flow (chat, streaming, RAG indexing, translation) |
| [docs/backend/overview.md](docs/backend/overview.md) | Backend project layout, configuration, dependency injection, running the API |
| [docs/backend/api.md](docs/backend/api.md) | Full REST API reference (every endpoint, request/response shape) |
| [docs/backend/chatbot.md](docs/backend/chatbot.md) | Sessions & messages: routers, services, repositories, prompts |
| [docs/backend/rag.md](docs/backend/rag.md) | RAG pipeline: chunking, embeddings, ChromaDB, retrieval, Moodle content loaders |
| [docs/backend/llm.md](docs/backend/llm.md) | LLM abstraction, Mistral integration, translation engine |
| [docs/backend/database.md](docs/backend/database.md) | Data model: tables, SQLAlchemy models, Moodle DB read access |
| [docs/moodle/overview.md](docs/moodle/overview.md) | Plugin structure, capabilities, settings, events, scheduled reindexing |
| [docs/moodle/backend.md](docs/moodle/backend.md) | PHP classes: `service`, `api_client`, external API (AJAX endpoints), HMAC signing |
| [docs/moodle/frontend.md](docs/moodle/frontend.md) | Chat widget UI: template, JS module, CSS, streaming rendering |
| [docs/setup/installation.md](docs/setup/installation.md) | Local setup from scratch: env vars, dependencies, plugin install, indexing courses |

---

## 🧠 What the system does today

- **Chat** — students/teachers chat with an AI tutor from a floating widget available on
  every Moodle page (dashboard, course pages, site index).
- **RAG (Retrieval-Augmented Generation)** — the assistant grounds its answers in real
  course materials (Moodle pages, book chapters, labels, section summaries, and PDF
  files) instead of only general knowledge, and cites its sources with clickable links
  back into Moodle.
- **Scoped retrieval** — a chat tied to one course only searches that course's material;
  a chat started outside a course searches across every course the user is enrolled in.
- **Streaming responses** — answers stream token-by-token over Server-Sent Events (SSE),
  with a "Stop" button that persists whatever was generated so far.
- **Automatic chat titles** — the first exchange in a session is used to generate a short
  descriptive title via the LLM.
- **Multilingual chat translation** — an existing conversation can be viewed in English,
  German, Russian, or Ukrainian; translations are cached per message/language pair so a
  language switch is only translated once.
- **Session management** — pin, rename, archive/unarchive, and permanently delete chats,
  with a "Today / Previous" sidebar grouping.
- **Automatic reindexing** — course content changes in Moodle (new/edited pages, modules,
  sections) automatically queue a background reindex job for that course via Moodle's
  adhoc task system.
- **Signed service-to-service calls** — every request from the Moodle plugin to the
  FastAPI backend is HMAC-signed and timestamped to prevent tampering and replay.

## 🚧 Not yet implemented

- Feedback collection (thumbs up/down buttons exist in the UI but are not wired up)
- Message regenerate / edit (buttons exist in the UI, not wired up)
- Analytics module (not scaffolded yet — no code, folders, or DB tables for it exist)
- File attachments in chat (button present, disabled)
- Chat export / share (buttons present, marked "coming soon")

## 🛠 Tech stack

- **Backend:** Python, FastAPI, SQLAlchemy, Pydantic / pydantic-settings
- **LLM:** Mistral AI (`mistralai` SDK), model configurable via `MISTRAL_MODEL`
- **RAG:** ChromaDB (persistent local vector store), `sentence-transformers`
  (`paraphrase-multilingual-mpnet-base-v2` by default), PyMuPDF for PDF text extraction,
  BeautifulSoup for HTML cleanup of Moodle content
- **Database:** MySQL (Moodle's own database — the backend reads/writes directly into it)
- **Moodle plugin:** PHP (Moodle local plugin `local_ai_system`), Moodle AMD/RequireJS
  JavaScript module, Mustache templates, `marked.js` (via CDN) for markdown rendering
- **Auth:** HMAC-SHA256 request signing between Moodle and the API, plus a separate
  internal API key for server-triggered endpoints (reindexing)

## 🏗 High-level architecture

```
Moodle page (any page, via local_ai_system_before_footer)
   → floating chat button → <iframe> → local/ai_system/index.php
        → amd/src/chatbot.js  (AMD module)
              → Moodle external API (AJAX)  — sessions, messages, rename, archive...
              → ajax/stream.php (raw cURL passthrough) — streaming chat only
                    ↓ HMAC-signed HTTP request
        FastAPI backend (api/)
              chatbot/routers → chatbot/services → chatbot/repositories → db/models
                                        ↓
                                 rag/ (retriever, vector store, embeddings)
                                        ↓
                                 llm/ (Mistral)
```

See [docs/architecture.md](docs/architecture.md) for the full breakdown.
