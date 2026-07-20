# Data Flow

This document walks through every major flow in the system step by step, referencing the
actual functions/files involved.

## 1. Page load — chat widget appears

1. `moodle-plugin/local/ai_system/lib.php` → `local_ai_system_before_footer()` runs on
   every page render. It checks `$PAGE->pagetype` against an allow-list
   (`site-index`, `my-index`, `course-index`) and, if matched, injects a floating button
   (`#ai-fab`) plus a hidden slide-in panel (`#ai-fab-panel`) containing an `<iframe>`.
2. The iframe's `src` is left empty until the user clicks the button (lazy-load), then set
   to `local/ai_system/index.php?embed=1`.
3. `index.php` runs `require_login()`, checks the `local_ai_system:use_chatbot`
   capability, fetches the user's existing sessions
   (`\local_ai_system\chatbot\service::get_sessions`) and enrolled courses
   (`enrol_get_users_courses`), and server-renders the `local_ai_system/chatbot` Mustache
   template with that data.
4. `$PAGE->requires->js_call_amd('local_ai_system/chatbot', 'init', [session_id, course_id])`
   boots the JS module (`amd/src/chatbot.js`, compiled to `amd/build/chatbot.min.js`),
   which binds all UI event listeners, groups sessions into Today/Previous, restores the
   saved theme from `localStorage`, and marks the course picker locked/unlocked based on
   whether the active session already has messages.

## 2. Creating a new session

- User clicks "New Chat" → `ChatBot.bindNewSession()` → `ChatBot.createNewSession()` →
  Moodle AJAX call `local_ai_system_create_session` with `{title, course_id}`.
- PHP: `chatbot_api::create_session()` → `service::create_session()` → `api_client::post()`
  signs the request and calls `POST /sessions` on the backend.
- Backend: `session_router.create_session()` → `SessionService.create_session()` →
  generates a UUID `session_id`, `SessionRepository.create()` inserts a row into
  `mdl_local_ai_system_sessions` with `is_active=1`, `title` as given (or `None`).
- The new session is prepended to the sidebar client-side immediately
  (`addSessionToSidebar`) — no full page reload.
- Note: a session can also be implicitly created the *first time a message is sent*
  without pressing "New Chat" first, via `ChatBot.ensureSession()` inside
  `sendMessageStream()`. This is what allows a completely fresh chatbot panel to accept a
  message right away.

## 3. Sending a message (non-streaming path)

Used by `MessageService.chat()` (backend) — exposed as `POST /sessions/{id}/messages`.
Currently the *streaming* path (below) is what the actual UI uses for user-initiated
sends; the non-streaming endpoint exists as a complete alternative implementation with
the same logic, useful for testing or non-streaming clients.

1. Router checks the session belongs to the requesting `X-User-Id`.
2. `MessageService.chat(session_id, content)`:
   - Loads existing messages to determine `is_first_message`.
   - `_resolve_search_scope(session)` decides retrieval scope: if `session.course_id` is
     set → `("course_{id}", None, [course_id])`; otherwise → look up all enrolled course
     ids via `CourseRepository.get_enrolled_course_ids` → `(None, course_ids, course_ids)`.
   - `_build_course_link_context(...)` turns the relevant course id(s) into ready-made
     markdown links (`chatbot/course_links.py`) so the LLM never has to construct a URL
     itself.
   - Saves the user's message (`create_user_message`).
   - Reloads full message history and calls `AIService.generate_response(history, ...)`.
   - Saves the assistant's reply (`create_assistant_message`).
   - If this was the first exchange and the session still has the default title
     (`"New Chat"`), calls `AIService.generate_title()` and updates the session.
   - Translates both messages for display if the session has a `language` set
     (`_translate_message`, using cached translations when available).
   - Returns `{user, assistant, title}`.

## 4. Sending a message (streaming path — what the UI actually uses)

This is the real end-to-end path triggered by pressing Send / Enter in the chat box.

```
chatbot.js: sendMessageStream(message)
  → appendMessage('user', message)              [optimistic UI update]
  → createAssistantBubble()                      [empty bubble, streaming target]
  → ensureSession()                               [create session if none yet]
  → fetch(POST /local/ai_system/ajax/stream.php, {session_id, message})
       ↓
  ajax/stream.php (plain PHP, NOT the Moodle external-API framework —
                    chosen specifically because Moodle's AJAX layer can't
                    stream a response body)
    → require_login() + capability check
    → HMAC-signs {content: message} the same way api_client.php does
    → curl_setopt(..., CURLOPT_WRITEFUNCTION, ...) streams bytes straight
      through to the browser as they arrive from the backend (ob_flush/flush
      per chunk, CURLOPT_BUFFERSIZE=1 for minimal buffering)
       ↓  POST /sessions/{session_id}/messages/stream   (SSE)
  message_router.stream_message()
    → MessageService.chat_stream(session_id, content)
        - same scope resolution + course-link building as the non-streaming path
        - saves the user message immediately
        - async for token in AIService.stream_response(...): yield token
        - after the loop, saves the full assistant message in one write
        - if first message: generates + saves a title
    → generator() in the router wraps each token as
      `data: {"token": "..."}\n\n`, then after the stream ends, emits
      `data: {"title": "..."}\n\n` (session title, possibly freshly generated,
      possibly unchanged) and finally `data: [DONE]\n\n`
       ↓ (all of the above re-streamed byte-for-byte through stream.php)
  chatbot.js: reads the fetch() response body via a ReadableStream reader,
    splits on newlines, parses each `data: ...` line as JSON:
      - if it has a "title" key → applyGeneratedTitle() updates the header
        and the sidebar entry
      - otherwise it's {"token": "..."} → appended to a running buffer,
        re-rendered into the bubble via marked.parse() on every token
    → on completion: sets the message timestamp, wires up the message
      action buttons (copy/regenerate/thumbs), unlocks course switching
      is already locked at send-time via setCourseLock(true)
```

### Retrieval inside `AIService.stream_response` / `generate_response`

Both the streaming and non-streaming paths share `AIService._build_system_prompt`:

1. `_build_retrieval_query(messages)` — concatenates the **last 2 user messages** (not
   just the latest one) as the text used for vector search. This is a deliberate
   heuristic documented in code: a short follow-up like *"which file is this from?"*
   carries almost no topical signal on its own and would otherwise cause retrieval to
   drift to unrelated chunks.
2. If a `collection_name` is set (course-scoped session):
   `Retriever.retrieve_as_context(query, collection_name, n_results=8, course_link=...)`.
3. Else if `course_ids` is set (global session, user has enrollments):
   `Retriever.retrieve_as_context_global(query, course_ids, n_results=8, course_links=...)`
   — searches every enrolled course's collection, merges results, sorts by score, takes
   the top 8 overall.
4. Else (no retriever, or no query, or no context found): falls back to
   `NO_CONTEXT_PROMPT` — a plain "answer from general SDG knowledge" system prompt.
5. If context *was* found: `RAG_SYSTEM_PROMPT + RAG_CONTEXT_TEMPLATE.format(context=...)`
   is used as the system prompt. This prompt strictly instructs the model to only state
   facts/citations that are literally present in the retrieved text, to explicitly say
   when the materials don't answer the question, and to always end with a `Source: ...`
   citation line copying the exact markdown link provided in the context tag (never
   inventing a URL).

### Stopping generation mid-stream

`ChatBot.state.controller` is an `AbortController` tied to the `fetch()` call. Pressing
Stop aborts the fetch (which also lets the PHP-side cURL passthrough terminate), then
immediately POSTs whatever text had accumulated so far
(`local_ai_system_save_partial_message` → `MessageService.create_partial_assistant_message`
→ inserted as a normal `role="assistant"` message) — so a stopped answer is not lost, it's
just shorter than it would have been.

## 5. Viewing an existing session

- Click a sidebar item → `ChatBot.loadSession(sessionId)` →
  `local_ai_system_get_messages` → `chatbot_api::get_messages()` →
  `service::get_messages()` → `GET /sessions/{id}/messages`.
- Backend: `MessageService.get_session_messages_for_display()` — loads all messages, and
  for each one calls `_translate_message(message, session.language)`. If the session has
  no `language` set, content is returned as-is (no translation call happens at all for
  the common case).
- The messages replace the container's content client-side (`appendMessage` for each),
  input/send button are enabled or disabled based on whether the session is archived, and
  the course picker is locked if the session already has messages.

## 6. Switching a session's display language

- User picks a language from the header dropdown → `bindLanguagePicker()` handler:
  1. `local_ai_system_update_session` with `{session_id, language}` — persists the choice
     on the session row (`SessionRepository.update`, using the `_UNSET` sentinel pattern
     so "not provided" and "explicitly reset to null" are distinguishable both in the
     Python repository and in the PHP external API's `UNSET` constant).
  2. `local_ai_system_get_messages` is called again — this re-triggers
     `_translate_message` for every message in the session, which will now find no cached
     translation for most/all of them (first time in this language) and calls
     `Translator.translate()` for each, caching the result in
     `mdl_local_ai_system_message_translations` before returning it.
  3. The UI shows a translating overlay while this happens
     (`showTranslatingOverlay`/`hideTranslatingOverlay`).
- On subsequent visits to the same session in the same language, translations are served
  straight from the cache table — no LLM calls at all.
- Selecting "Original" clears `language` back to `null` (empty string from the dropdown is
  translated to `None` on the PHP side before being sent, to match the Python side's
  semantics) and the raw, untranslated content is shown again.

## 7. Session management actions

| Action | Frontend entry point | AJAX method | Backend |
|---|---|---|---|
| Rename | rename popup → Save | `local_ai_system_update_session` | `SessionService.update_session` |
| Archive | context menu → Archive | `local_ai_system_archive_session` | `SessionService.archive_session` (`is_active=0`) |
| Unarchive | archive dropdown item → context menu | `local_ai_system_dearchive_session` | `SessionService.dearchive_session` (`is_active=1`) |
| Delete | context menu → Delete (confirm dialog) | `local_ai_system_delete_session` | `SessionService.delete_session` (hard delete, `DELETE FROM`) |
| Pin | star icon / context menu | *client-side only* — `ChatBot.state.pinned`, not persisted to the backend at all | — |

Archived sessions are shown in a separate dropdown, disable the message input, and lock
the course picker; deleting or archiving the currently-open session clears the chat panel
back to its empty state.

## 8. Course content indexing (RAG ingestion)

### 8a. Manual/triggered indexing

`POST /rag/index/{course_id}` (internal-API-key protected) →
`rag_router.index_course()`:
1. Verifies the course exists (`CourseRepository.course_exists`).
2. Schedules `RagService.index_course_background(course_id, pipeline)` as a FastAPI
   `BackgroundTask` — the HTTP response (`202 Accepted`) returns immediately, indexing
   happens after.
3. `index_course_background` opens its **own** DB session (`SessionLocal()`, independent
   of the request-scoped one, since the original request has already completed by the
   time this runs), deletes any existing `course_{id}` ChromaDB collection, then runs
   `CourseIndexer.index_course(course_id, reset=False)`.

`CourseIndexer.index_course`:
1. `MoodleDBLoader.load_course(course_id)` — pulls text content directly from Moodle's DB:
   course section summaries, `mdl_page` content, `mdl_book_chapters`, `mdl_label` intros.
   All HTML is stripped via BeautifulSoup (`clean_html`). Documents under 50 characters
   are discarded.
2. `MoodlePDFLoader.load_course_pdfs(course_id)` — finds every PDF file attached to the
   course (`mdl_files` joined against `mdl_context`, filtered to
   `contextlevel=70` course-module contexts belonging to the course, or `contextlevel=50`
   the course context itself), locates each file on disk in
   `MOODLEDATA_PATH/filedir/XX/YY/{contenthash}` (Moodle's content-addressed storage
   layout), and extracts text with PyMuPDF (`fitz`). Also builds a direct
   `pluginfile.php` download URL for each PDF (`_build_file_url`) so retrieved chunks can
   cite a clickable link straight to the source file.
3. All documents (DB-sourced + PDF-sourced) go through
   `IngestionPipeline.ingest_many()` → for each document: `TextChunker.split()` →
   `EmbeddingModel.embed_chunks()` → `VectorStore.add_embedded_chunks()`, storing into the
   `course_{id}` ChromaDB collection.
4. Returns a summary (`documents`, `chunks`, `success`).

`POST /rag/index-all` does the same for every real course in Moodle
(`CourseRepository.get_all_course_ids`, excluding site id `1`), **sequentially** —
deliberately not in parallel, to avoid multiple courses competing for the same embedding
model/CPU/GPU and to keep progress logs readable.

`GET /rag/status/{course_id}` — reports whether a collection exists, how many chunks it
holds, and how many *distinct* source documents contributed to it (derived from unique
`source_name` values in the collection's metadata).

### 8b. Automatic reindexing on content change

1. Moodle fires one of: `course_created`, `course_updated`, `course_module_created`,
   `course_module_updated`, `course_module_deleted`, `course_section_updated`.
2. `db/events.php` routes all of them to `observer::course_changed()`.
3. `observer::course_changed()` ignores the site course (id `1`) and calls
   `queue_reindex($courseid)`, which first checks `has_pending_task()` — scanning the
   `task_adhoc` table for an already-queued `reindex_course_task` for the same course, to
   avoid stacking up duplicate reindex jobs when an editor makes several rapid edits.
4. If no duplicate is pending, a `reindex_course_task` adhoc task is queued via
   `\core\task\manager::queue_adhoc_task()`.
5. On Moodle's next cron run, `reindex_course_task::execute()` calls
   `api_client::post_internal("/rag/index/{courseid}", ['reset' => true])` — the
   `post_internal` variant that adds the `X-Internal-Api-Key` header required by
   `verify_internal_api_key`.

## 9. Retrieval query flow at answer time (summary)

```
user message(s)
   → _build_retrieval_query(): last 2 user messages, concatenated
   → embed via EmbeddingModel.embed_text()
   → VectorStore.search(collection, query_embedding, n_results, where?)
        → ChromaDB collection.query(...) → cosine distance → score = 1 - distance
   → Retriever filters by min_score (default 0.3) and sorts by score desc
   → (global mode only) merge across all enrolled collections, re-sort, truncate to n
   → format as "[Course: <link> — Source: <link-or-filename>]\n<chunk text>" blocks
   → inserted into RAG_CONTEXT_TEMPLATE inside the system prompt
   → sent to Mistral along with the full conversation history
```
