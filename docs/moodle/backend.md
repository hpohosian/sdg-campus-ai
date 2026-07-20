# Moodle Plugin — PHP Backend Classes

## `classes/external/api_client.php` — signed HTTP client

`api_client` is the single place that talks HTTP to the FastAPI backend. Constructed
fresh (reads `api_base_url`, `api_secret`, `internal_api_key` from plugin config) each
time a `service` object is instantiated.

Every request goes through the private `request($method, $path, $body, $user_id,
$internal)` method:

1. Builds the JSON payload (`json_encode($body, JSON_UNESCAPED_UNICODE)`, or an empty
   string if `$body` is empty).
2. Computes `$signature = hash_hmac('sha256', $timestamp . $payload, $this->secret)`.
3. Sets headers: `Content-Type`, `X-Timestamp`, `X-Signature`, `X-User-Id` (resolved from
   the explicit `$user_id` param, or extracted from the body's `user_id`/`userid` key as
   a fallback via `extractUserId`).
4. If `$internal` is true, also sets `X-Internal-Api-Key`.
5. Uses Moodle's own `\curl` wrapper class (`ignore_security_hosts = true`, needed for
   calling a local/non-HTTPS backend during development) to actually perform the
   GET/POST/PUT/DELETE.
6. Logs method, URL, request body, raw response, and decoded response to
   **`$CFG->dirroot . '/debug.log'`** on every single call via a private `log()` helper.

Public methods: `get`, `post`, `put`, `delete` (all unsigned-as-internal), plus
`post_internal` (sets the internal flag, used only by the reindex task).

> **Operational note — verbose file logging is always on.** The `log()` method writes to
> `debug.log` in Moodle's webroot on *every* API call, unconditionally (not gated behind
> `$CFG->debug` or the plugin's own `DEBUG` setting). This is extremely useful during
> development but should be disabled or made conditional before any production
> deployment — it writes full request/response bodies (which may include user chat
> content) to a plaintext file inside the web root.

> **Error handling note:** `request()` throws a generic
> `new \moodle_exception('apierror', 'local_ai_system')` on any cURL-level error (e.g.
> connection refused, timeout) — but there is **no corresponding
> `$string['apierror']`** entry in `lang/en/local_ai_system.php`, so this exception would
> render Moodle's fallback "undefined string" placeholder rather than a clear error
> message. Worth adding the missing language string.

## `classes/chatbot/service.php` — high-level chat API

`service` is a thin façade over `api_client`, translating plugin-level concepts (create a
session, send a message, etc.) into the specific `api_client` calls with the specific
paths/bodies the FastAPI backend expects. This is the class both `index.php` and
`chatbot_api.php` (the external API) go through — neither of them talks to `api_client`
directly.

Every method just maps 1:1 onto a backend REST endpoint (see
[backend/api.md](../backend/api.md) for the exact request/response shapes):

| `service` method | Backend call |
|---|---|
| `create_session($userid, $title, $course_id)` | `POST /sessions` |
| `get_sessions($userid)` | `GET /sessions` |
| `get_session($session_id)` | `GET /sessions/{id}` |
| `update_session($session_id, $data, $userid)` | `PUT /sessions/{id}` |
| `delete_session($session_id, $userid)` | `DELETE /sessions/{id}` |
| `archive_session($session_id, $userid)` | `PUT /sessions/archive/{id}` |
| `dearchive_session($session_id, $userid)` | `PUT /sessions/dearchive/{id}` |
| `get_messages($session_id, $userid)` | `GET /sessions/{id}/messages` |
| `send_message($session_id, $message)` | `POST /sessions/{id}/messages` (non-streaming — not used by the live UI, which uses `ajax/stream.php` instead) |
| `save_partial_message($session_id, $content)` | `POST /sessions/{id}/messages/partial` |

Note `send_message` does not currently pass `$userid` through explicitly to
`api_client::post` — it relies on the fallback `extractUserId($body)` path inside
`api_client`, but the body it builds (`['message' => $message]`) doesn't include a
`user_id` key either, so the `X-User-Id` header on this specific call would end up as
`0`. In practice this doesn't cause a visible bug today because the live UI never calls
this method (it uses the streaming path instead, which sets `X-User-Id` directly from
`ajax/stream.php`'s own `$USER->id`) — but it would need fixing if this method is ever
wired up or reused.

## `classes/external/chatbot_api.php` — the AJAX surface

Implements Moodle's `external_api` pattern: each operation is a
`*_parameters()` / actual method / `*_returns()` triple, registered in `db/services.php`
and called from JavaScript via `core/ajax`. This is how everything **except streaming**
reaches the backend.

Standard shape repeated for every function:
1. `self::validate_parameters(...)` — type-checks and coerces input against the declared
   parameter spec.
2. `self::validate_context(\context_system::instance())`.
3. `require_capability('local_ai_system:use_chatbot', $context)`.
4. Delegate to a new `\local_ai_system\chatbot\service()` instance.
5. Return data matching the declared `*_returns()` structure.

Functions exposed (see `db/services.php` for the exact Moodle service-function names
used from JS): `get_sessions`, `create_session`, `update_session`, `delete_session`, `archive_session`,
`dearchive_session`, `get_messages`, `stream_message` *(declared with parameters/returns,
but **not** registered in `db/services.php` and not called by the JS module — streaming
goes through `ajax/stream.php` instead, bypassing the external-API framework entirely,
since Moodle's AJAX layer doesn't support a streamed response body)*,
`save_partial_message`.

Note `service.php`'s `get_session()` method (used internally, e.g. for ownership checks)
has no corresponding external function in `chatbot_api.php` at all — it's only reachable
from PHP code, not from JavaScript.

**`update_session`'s optional-field handling** is worth calling out specifically since it
mirrors a pattern also used on the Python side: parameters default to a private
`UNSET = '__unset__'` sentinel string rather than `null`, because Moodle's external-API
parameter validation doesn't cleanly distinguish "not provided" from "explicitly null"
the way the sentinel trick does. The handler only includes a key in the outgoing `$data`
array if the value differs from `UNSET`; an empty-string `language` is explicitly
converted to PHP `null` before being sent, to match the semantics `SessionRepository`
expects on the Python side (`""` would otherwise be treated as "set language to the
literal empty string" rather than "reset to original").

## `db/services.php` — service registration

Registers each external function (`local_ai_system_get_sessions`,
`local_ai_system_create_session`, etc.) with `ajax: true` and `loginrequired: true`,
which is what makes them callable from `core/ajax` in JavaScript without a separate
mobile/web-service token setup. `stream_message` is **not** in this file (see note
above).

## `classes/observer.php` and `classes/task/reindex_course_task.php`

Covered in detail in [moodle/overview.md](overview.md#events--automatic-reindexing-dbeventsphp--observerphp)
and [data-flow.md](../../data-flow.md#8b-automatic-reindexing-on-content-change).

## `ajax/stream.php` — the one endpoint outside the external-API framework

Exists specifically because Moodle's `core/ajax` JS module and the `external_api` PHP
framework are built around request/response calls, not long-lived streamed HTTP bodies.
`stream.php` is a plain PHP script (not an `external_api` class) that:

1. Does its own `require_login()` + capability check (since it bypasses the framework
   that would normally do this).
2. Reads `session_id`/`message` from the POST body.
3. Signs a request the same way `api_client.php` does (duplicated HMAC logic, not shared
   code — a small maintenance risk: if the signing scheme ever changes, it must be
   updated in two places).
4. Uses raw cURL with `CURLOPT_WRITEFUNCTION` to forward each chunk of the backend's SSE
   response straight to the browser as it arrives (`ob_flush()` + `flush()` per chunk,
   `CURLOPT_BUFFERSIZE = 1` to minimize buffering delay), checking
   `connection_aborted()` so it stops cleanly if the browser disconnects (e.g. the user
   pressed Stop, which aborts the `fetch()` on the JS side).

Its FastAPI target URL is hard-coded (`http://127.0.0.1:8001`) rather than read from the
`api_base_url` admin setting — see the reminder in
[moodle/overview.md](overview.md#admin-settings-settingsphp).
