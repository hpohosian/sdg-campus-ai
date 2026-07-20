# Moodle Plugin Overview

`moodle-plugin/local/ai_system` is a standard Moodle **local plugin** (component name
`local_ai_system`). It integrates the AI chatbot into any Moodle installation without
modifying Moodle core.

## Plugin metadata (`version.php`)

```php
$plugin->version   = 2026071309;    // YYYYMMDDXX
$plugin->requires  = 2021051700;    // minimum Moodle version
$plugin->component = 'local_ai_system';
```

## File map

```
local/ai_system/
├── index.php              main chat page (rendered inside the iframe)
├── lib.php                injects the floating button on every relevant page
├── settings.php           admin settings page (API URL + two secrets)
├── styles.css              all chat widget styling
├── version.php
│
├── ajax/
│   ├── create_session.php  legacy/simple direct endpoint (see note below)
│   └── stream.php          raw cURL passthrough for SSE streaming
│
├── classes/
│   ├── chatbot/service.php         high-level PHP API used by index.php + external API
│   ├── external/
│   │   ├── api_client.php          low-level signed HTTP client to the FastAPI backend
│   │   └── chatbot_api.php         Moodle "external functions" (the AJAX surface)
│   ├── observer.php                event → reindex-task wiring
│   └── task/reindex_course_task.php  adhoc task, runs on cron
│
├── templates/chatbot.mustache      server-rendered chat UI shell
├── amd/
│   ├── src/chatbot.js               AMD module source (interactivity)
│   └── build/chatbot.min.js         compiled/minified build actually loaded by Moodle
│
├── db/
│   ├── install.xml         schema for the plugin's 4 tables
│   ├── services.php        registers the external functions Moodle exposes over AJAX
│   ├── events.php          maps Moodle core events → observer::course_changed
│   └── access.php          capability definitions
│
└── lang/en/local_ai_system.php   UI strings (English only)
```

> **`ajax/create_session.php` vs. the external API:** the plugin has *two* separate ways
> to create a session — the Moodle "external function"
> `local_ai_system_create_session` (via `chatbot_api::create_session`, used by
> `chatbot.js`'s actual `createNewSession()`/`ensureSession()` calls), and a standalone
> `ajax/create_session.php` script that does the same thing more directly (its own
> `require_login()` + capability check + `service->create_session()` call, returning raw
> JSON). The JS module does not appear to call `ajax/create_session.php` at all — only
> `ajax/stream.php` is used outside the Moodle external-API framework. `create_session.php`
> looks like an earlier, simpler approach that was superseded once the full external-API
> layer (`chatbot_api.php`) was built out, but was never removed.

## Capabilities (`db/access.php`)

| Capability | Context | Granted to |
|---|---|---|
| `local_ai_system:use_chatbot` | system | user, student, teacher, editingteacher, manager (i.e. everyone) |
| `local_ai_system:view_history` | system | teacher, editingteacher, manager |

`view_history` is **defined but not currently enforced anywhere** in the codebase — no
`require_capability('local_ai_system:view_history', ...)` call exists in any file. It
appears to be a placeholder for a not-yet-built teacher-facing chat history/analytics
view.

## Admin settings (`settings.php`)

Exposed under Site administration → Plugins → Local plugins → AI System:

| Setting | Type | Default | Purpose |
|---|---|---|---|
| `api_base_url` | text | `http://127.0.0.1:8001` | FastAPI backend base URL — used by `api_client.php` |
| `internal_api_key` | password (unmasked) | empty | must match backend's `INTERNAL_API_KEY`, used by the reindex task |
| `api_secret` | password (unmasked) | empty | HMAC shared secret — must match backend's `MOODLE_SECRET`, used by every signed request |

**Reminder:** `ajax/stream.php` has its own hard-coded `$base_url = 'http://127.0.0.1:8001'`
and does **not** read `api_base_url` from settings — if the backend's address ever
changes, this file must be updated by hand in addition to the settings page (see
[backend/overview.md](../backend/overview.md#running-the-api)).

## Where the widget appears (`lib.php`)

`local_ai_system_before_footer()` is a Moodle callback invoked on every page render. It
checks `$PAGE->pagetype` against an allow-list — `site-index`, `my-index`,
`course-index` (substring match, so e.g. `course-index-category` would also match) — and
only injects the floating button/panel markup on matching pages. A commented-out line
(`// $show = true;`) is left in place as a documented way to force it onto every page
during testing.

The injected markup is a self-contained floating action button (`#ai-fab`), a dimmed
backdrop, and a slide-in side panel containing a lazily-loaded `<iframe>` pointing at
`local/ai_system/index.php?embed=1`. All of this HTML/CSS/JS is generated inline inside
the PHP function as a big string, rather than living in `templates/chatbot.mustache` or
`styles.css`/`amd/src/chatbot.js` — this is a *separate*, smaller piece of UI from the
main chat widget itself (the fab button/panel chrome vs. the chat contents inside the
iframe).

## Events → automatic reindexing (`db/events.php` + `observer.php`)

See [backend/overview.md](../backend/overview.md) and
[data-flow.md](../../data-flow.md#8b-automatic-reindexing-on-content-change) for the full
sequence. Summary: six Moodle course-content events are observed
(`course_created`, `course_updated`, `course_module_created`, `course_module_updated`,
`course_module_deleted`, `course_section_updated`); each queues a deduplicated
`reindex_course_task` adhoc task, which runs on Moodle's cron and calls the backend's
`/rag/index/{course_id}` internal endpoint.

## Database schema (`db/install.xml`)

Defines the 4 tables described in
[backend/database.md](../backend/database.md#tables-owned-by-this-plugin) —
`local_ai_system_sessions`, `local_ai_system_messages`,
`local_ai_system_message_translations`, `local_ai_system_logs` (Moodle automatically
prefixes these with its configured table prefix, `mdl_` in the dev `.env`, giving the
`mdl_local_ai_system_*` names used throughout the Python backend).
