# REST API Reference

Base URL (dev): `http://127.0.0.1:8001`

All endpoints below (except `/rag/index*`) expect an `X-User-Id` header identifying the
calling Moodle user (temporary auth mechanism — see
[backend/overview.md](overview.md#dependency-injection-dependenciespy)). Requests coming
from the Moodle plugin also carry `X-Timestamp` / `X-Signature` (HMAC) headers, though
note the middleware that verifies them (`HMACAuthMiddleware`) is not currently mounted in
`main.py` — see [architecture.md](../architecture.md#security-model).

---

## Sessions — `chatbot/routers/session_router.py`

### `POST /sessions`
Create a new chat session.

Request body (`CreateSessionRequest`):
```json
{ "course_id": 12, "title": "New Chat" }
```
Both fields optional; `course_id: null` creates a "global" session that searches across
all enrolled courses.

Response (`SessionResponse`, `200`):
```json
{
  "session_id": "b3f1...-uuid",
  "user_id": 5,
  "course_id": 12,
  "title": "New Chat",
  "language": null,
  "is_active": 1
}
```

### `GET /sessions/{session_id}`
Fetch one session. `403` if the session doesn't belong to the requesting user.

### `GET /sessions`
List all sessions for the current user (both active and archived), most recently updated
first.

### `PUT /sessions/{session_id}`
Update a session's title and/or display language.

Request body (`UpdateSessionRequest`):
```json
{ "title": "Renamed chat", "language": "de" }
```
Both fields optional. **Field-presence matters**: the router distinguishes "field not
sent at all" from "field sent as empty string / null" using pydantic's
`model_fields_set`. Omitting `language` leaves it unchanged; sending `"language": ""`
explicitly resets it to `None` (shows original, untranslated content).

### `PUT /sessions/archive/{session_id}`
Soft-delete: sets `is_active = 0`. Response: `{"session_id": "...", "status": "archived"}`.

### `PUT /sessions/dearchive/{session_id}`
Reverses archive: sets `is_active = 1`. Response: `{"session_id": "...", "status": "dearchived"}`.

### `DELETE /sessions/{session_id}`
Hard delete — removes the row and (implicitly, since messages aren't cascade-checked
elsewhere) leaves any associated messages orphaned in the `messages` table (no explicit
cascade delete is implemented for messages when a session is deleted — see
[backend/database.md](database.md) for the caveat). Response:
`{"status": "deleted permanently"}`. `404` if the session doesn't exist.

---

## Messages — `chatbot/routers/message_router.py`

All routes are nested under `/sessions/{session_id}/messages`.

### `GET /sessions/{session_id}/messages`
Returns the full message history for display (`list[MessageResponse]`), translated into
the session's `language` if one is set.

```json
[
  { "id": 1, "session_id": "...", "role": "user", "content": "...", "tokens_used": null, "created_at": 1752963600 },
  { "id": 2, "session_id": "...", "role": "assistant", "content": "...", "tokens_used": null, "created_at": 1752963605 }
]
```

### `POST /sessions/{session_id}/messages`
Non-streaming send: saves the user's message, generates a full assistant response
(RAG-grounded if applicable), saves it, and — if this is the first exchange and the
session still has the default title — generates a title.

Request body (`SendMessageRequest`): `{"content": "..."}`

Response:
```json
{
  "user": { "id": 3, "session_id": "...", "role": "user", "content": "...", "tokens_used": null, "created_at": 1752963700 },
  "assistant": { "id": 4, "session_id": "...", "role": "assistant", "content": "...", "tokens_used": null, "created_at": 1752963705 },
  "title": "Photosynthesis basics"   // null unless a title was just generated
}
```

### `POST /sessions/{session_id}/messages/stream`
Streaming send — this is the path the actual UI uses. Returns
`text/event-stream` (SSE). Each event is one of:

```
data: {"token": "..."}\n\n           # repeated, one per generated token
data: {"title": "..."}\n\n           # sent once, after generation completes
                                      # (title may be unchanged/null-equivalent
                                      #  if this wasn't the first exchange)
data: [DONE]\n\n                     # terminal event
```

The user message is persisted before streaming starts; the full assistant message is
persisted only after the stream completes (so an aborted/errored stream, unless
explicitly saved via the `/partial` endpoint below, does not leave a partial message in
the database).

### `POST /sessions/{session_id}/messages/partial`
Persists a partial assistant message — called by the frontend after the user presses
"Stop" mid-stream, so the partially generated answer isn't lost.

Request body: `{"content": "..."}` (the partial text accumulated so far)

Response (`MessageResponse`): the newly created assistant message row. `400` if the
content is invalid per `create_partial_assistant_message`'s validation (empty content
raises `ValueError`, mapped to `400`).

---

## RAG — `chatbot/routers/rag_router.py`

These endpoints require an `X-Internal-Api-Key` header matching `INTERNAL_API_KEY`
(except `GET /rag/status/{course_id}`, which is unauthenticated). They are intended to be
called by the Moodle-side scheduled task, not by the chat UI directly.

### `POST /rag/index/{course_id}`
Triggers indexing of a single course in the background.

Request body (`IndexCourseRequest`): `{"reset": true}` (note: the `reset` flag from the
request body is currently accepted but not actually threaded through to
`indexer.index_course(course_id, reset=False)` — the background task always deletes and
rebuilds the collection unconditionally inside `RagService.index_course_background`
before calling the indexer, so in practice the collection is always reset regardless of
this flag's value).

Response (`RagStatusResponse`, `202 Accepted`):
```json
{
  "course_id": 12,
  "collection_name": "course_12",
  "documents_indexed": 0,
  "chunks_indexed": 0,
  "success": true,
  "message": "Course indexing pipeline successfully pushed to background worker."
}
```
This response reflects only that the background job was *queued*, not its outcome — poll
`GET /rag/status/{course_id}` to see the real result once indexing finishes. `404` if the
course doesn't exist in Moodle.

### `GET /rag/status/{course_id}`
Reports the current indexed state of a course's ChromaDB collection.

Response (`RagStatusResponse`):
```json
{
  "course_id": 12,
  "collection_name": "course_12",
  "documents_indexed": 4,
  "chunks_indexed": 87,
  "success": true,
  "message": "OK"
}
```
If the collection doesn't exist yet: `success: false`, `message: "Collection does not exist"`.

### `POST /rag/index-all`
Triggers sequential background indexing of every real course in Moodle.

Response (`IndexAllResponse`, `202 Accepted`):
```json
{ "total_courses": 14, "message": "Indexing pipeline started for 14 courses." }
```

---

## Error responses

Standard FastAPI/Pydantic validation errors (`422`) apply to malformed request bodies.
Domain errors surfaced by the code:

| Status | When |
|---|---|
| `401` | missing `X-User-Id` header (or `"0"`); missing/invalid internal API key on `/rag/index*` |
| `400` | non-integer `X-User-Id`; invalid content for `/messages/partial` |
| `403` | session exists but doesn't belong to the requesting user |
| `404` | session not found (on delete); course not found (on `/rag/index/{course_id}`) |

Note that `ValueError("Session not found")` raised inside services for **most** other
routes (e.g. `get_session`, `chat`) is *not* currently caught and converted to a `404` by
those routers — it will surface as an unhandled `500 Internal Server Error` unless
FastAPI's default exception handling intercepts it. Only `delete_session` explicitly
catches `ValueError` and converts it to `404`.
