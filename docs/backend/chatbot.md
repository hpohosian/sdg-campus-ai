# Chatbot Module (`api/chatbot/`)

This module owns sessions, messages, and the orchestration between them and the AI/RAG
layers. It does **not** contain the RAG or LLM implementations themselves (those live in
`api/rag` and `api/llm`) — it consumes them.

## Schemas (`schemas.py`)

Pydantic models used as FastAPI request/response bodies:

| Model | Used by | Notes |
|---|---|---|
| `CreateSessionRequest` | `POST /sessions` | `course_id`, `title` both optional |
| `SessionResponse` | most session endpoints | `from_attributes=True` — built directly from the ORM object |
| `UpdateSessionRequest` | `PUT /sessions/{id}` | `title`, `language` both optional |
| `SendMessageRequest` | message send endpoints | just `content: str` |
| `MessageResponse` | message endpoints | `from_attributes=True` |
| `IndexCourseRequest` | `POST /rag/index/{id}` | `reset: bool = True` (see caveat in [api.md](api.md)) |
| `RagStatusResponse` | RAG endpoints | indexing status/progress |
| `IndexAllResponse` | `POST /rag/index-all` | just a count + message |

## Prompts (`prompts.py`)

All LLM system prompts live in one file, as plain string constants:

- `SYSTEM_PROMPT`, `EXPLAIN_PROMPT`, `SHORT_PROMPT`, `TUTOR_PROMPT` — earlier/simple
  prompt variants. Not currently referenced by `AIService` (which uses the RAG-specific
  prompts below) — kept in the file, presumably for earlier experimentation or possible
  future use as alternate modes.
- `RAG_SYSTEM_PROMPT` — the main system prompt used whenever retrieved context exists.
  Key rules it enforces on the model:
  - Only state a specific fact/date/citation if it's **literally present** in the
    retrieved materials — never supply a citation from the model's own training data.
  - Must end every answer with a `Source: ...` line, copying course/file markdown links
    **exactly** as given in the context tags — never inventing or reconstructing a URL.
  - If the materials don't (fully) answer the question, must say so explicitly and first,
    before optionally adding clearly-labeled general knowledge.
  - Must not present invented examples as if they came from the course materials.
- `RAG_CONTEXT_TEMPLATE` — wraps the retrieved context blocks with instructions to answer
  using *only* what's provided.
- `NO_CONTEXT_PROMPT` — fallback prompt used when there's no retriever, no query, or no
  matching context — a plain "answer from general SDG knowledge" tutor persona.
- `_TITLE_SYSTEM_PROMPT` (in `ai_service.py`, not `prompts.py`) — instructs the model to
  produce a 3-6 word title in the same language as the conversation, no quotes/punctuation.

## `course_links.py`

Small, deliberately trivial module whose entire purpose is a security/reliability
property: **the LLM never constructs a Moodle URL itself.**

- `format_course_link(course_id, course_name)` → `"[CourseName](http://.../course/view.php?id=12)"`.
  Falls back to `f"Course {course_id}"` as the display name if the lookup failed (e.g.
  deleted course), so citations still degrade gracefully instead of breaking.
- `build_course_links(course_names: dict[int, str])` → bulk version, `{id: name}` →
  `{id: markdown_link}`, used for global (multi-course) sessions.

These ready-made strings are inserted into the retrieval context tags
(`[Course: <link> — Source: <link>]`) that `RAG_SYSTEM_PROMPT` instructs the model to copy
verbatim into its citation line.

## Services

### `SessionService`

Thin orchestration over `SessionRepository`. Notable behaviors:
- `create_session` generates the `session_id` as a `str(uuid4())` in the service layer
  (not the DB) — Moodle's plugin never sees or assigns this ID itself.
- `update_session` accepts a `language` parameter defaulting to a private `_UNSET`
  sentinel object (imported from the repository module) — this is how "field not
  provided" is distinguished from "field explicitly set to `None`" all the way down to
  the SQL UPDATE.
- `archive_session` / `dearchive_session` both go through a single `set_active(id, 0|1)`
  repository method.

### `MessageService`

The most complex service in the module — owns the full chat orchestration.

- **`_resolve_search_scope(session)`** — the single place that decides retrieval scope
  for a session: course-scoped (`session.course_id` set) vs. global (falls back to the
  user's enrolled course ids via `CourseRepository`). Returns
  `(collection_name, course_ids, relevant_course_ids)` — the first two are what get
  passed to `AIService`, the third is used only for building course-link citations.
- **`_build_course_link_context(...)`** — resolves course id(s) to human-readable names
  (`CourseRepository.get_course_names`, one bulk query) and builds markdown links via
  `course_links.py`. Returns either a single `course_link` (course-scoped) or a
  `course_links` dict (global).
- **`chat(session_id, content)`** — the non-streaming send path. See
  [data-flow.md](../data-flow.md#3-sending-a-message-non-streaming-path) for the full
  sequence.
- **`chat_stream(session_id, content)`** — an async generator yielding tokens as they
  arrive from `AIService.stream_response`; persists the user message before streaming and
  the complete assistant message after. Also handles first-message title generation,
  mirroring the non-streaming path.
- **`create_partial_assistant_message(session_id, content)`** — used by the
  `/messages/partial` endpoint when a stream is aborted by the user.
- **`_translate_message(message, target_language)`** — checks
  `MessageTranslationRepository.get()` for a cached translation first; only calls
  `Translator.translate()` (an LLM call) on a cache miss, then persists the result.
  Returns the original content unchanged if `target_language` is falsy.
- **`get_session_messages_for_display(session_id)`** — the method backing
  `GET /sessions/{id}/messages`; translates every message per the session's `language`.

### `AIService`

Sits between `MessageService` and the raw `BaseLLM` — this is where retrieval and prompt
construction happen. See [data-flow.md](../data-flow.md#retrieval-inside-aiservicestream_response--generate_response)
for the retrieval-query construction heuristic
(`_build_retrieval_query`, last-2-user-messages) and the priority order for choosing a
system prompt (course-scoped → global → no-context fallback).

`_format(messages)` normalizes both dict-shaped and ORM-object-shaped message inputs into
plain `{"role", "content"}` dicts for the LLM call, and trims any trailing assistant
message(s) off the end of the history before sending (defensive cleanup — a trailing
assistant turn would otherwise be sent as if it were the model's own prior turn with no
new user input to respond to).

`generate_title(user_message, assistant_message)` — a separate, cheap LLM call using
`_TITLE_SYSTEM_PROMPT`; strips quotes and truncates to 255 characters (matching the
`title` column's `VARCHAR(255)` limit in both the Python model and Moodle's `install.xml`).

### `RagService`

Orchestrates background indexing (see [data-flow.md](../data-flow.md#8-course-content-indexing-rag-ingestion)
for the full sequence) and exposes `get_all_course_ids()` (delegates to
`CourseRepository`) for the `/rag/index-all` endpoint. Deliberately indexes courses
**sequentially**, not with `asyncio.gather` or similar, to avoid resource contention on
the embedding model.

## Repositories

- **`SessionRepository`** — CRUD over `mdl_local_ai_system_sessions`. Also defines the
  small in-module `Session` domain class (a plain constructor object, not a Pydantic
  model, not the SQLAlchemy model) that `SessionService.create_session` builds before
  handing off to the repository — an extra indirection layer between "what the service
  wants to create" and "what actually gets written," though in practice the repository
  immediately re-wraps it into a `SessionModel` anyway.
- **`MessageRepository`** — `get_by_session` (ordered by `created_at` ascending) and
  `create`.
- **`MessageTranslationRepository`** — `get(message_id, language)` /
  `create(message_id, language, content)`, backed by the unique constraint on
  `(message_id, language)`.
- **`RagRepository`** — a thin pass-through wrapper around `VectorStore` exposing just
  `collection_exists` / `delete_collection`, used by `RagService` so it doesn't depend on
  the RAG module's `VectorStore` class directly.

## Routers

See [api.md](api.md) for the full endpoint-by-endpoint reference. Structurally, every
router follows the same shape: resolve dependencies via `Depends(get_*)`, verify
ownership (`session.user_id != user_id → 403`) where relevant, delegate to the service,
map the result onto a response schema.
