# Database

The backend does not have its own database — it connects to the **same MySQL instance
Moodle uses** (`DATABASE_URL` in `.env`), adds a handful of its own tables, and reads
several of Moodle's native tables directly via raw SQL.

## Connection (`db/connection.py`)

Plain SQLAlchemy setup: `create_engine(settings.DATABASE_URL)`,
`sessionmaker(autoflush=False, autocommit=False, expire_on_commit=True)`. `get_db()` is a
FastAPI dependency (generator) that yields a session and closes it after the request —
one DB session per request, matching FastAPI's usual pattern.

Note: each ORM model file (`session.py`, `message.py`, `message_translation.py`) declares
its own `Base = declarative_base()` rather than sharing one `Base` across the models —
functionally fine here since none of the three ever needs cross-model relationship
mapping or `Base.metadata.create_all()`-style automatic schema creation (schema is
instead defined declaratively in the Moodle plugin's `db/install.xml`, applied through
Moodle's own installer), but it does mean these three models cannot participate in a
single shared metadata object if that were ever needed later (e.g. for Alembic
migrations across all three at once).

## Tables owned by this plugin

Schema authority is `moodle-plugin/local/ai_system/db/install.xml` (applied by Moodle's
own plugin installer/upgrader) — the Python `db/models/*.py` files are SQLAlchemy mirrors
of that schema, not the source of truth. Table names are prefixed
`mdl_local_ai_system_...` to sit alongside Moodle's own `mdl_*` tables.

### `mdl_local_ai_system_sessions`
*(ORM: `db/models/session.py` → `SessionModel`)*

| Column | Type | Notes |
|---|---|---|
| `id` | int, PK | |
| `session_id` | char(64), unique, indexed | app-level UUID, not the numeric PK |
| `user_id` | int | Moodle user id |
| `course_id` | int, nullable | `NULL` = global (all-enrolled-courses) session |
| `title` | char(255), nullable | |
| `language` | char(5), nullable | display-translation target, e.g. `de`/`ru`/`uk`; `NULL` = show original |
| `created_at` | int | unix timestamp |
| `updated_at` | int | unix timestamp, bumped on rename/language change |
| `is_active` | int, default 1 | `0` = archived |

### `mdl_local_ai_system_messages`
*(ORM: `db/models/message.py` → `MessageModel`)*

| Column | Type | Notes |
|---|---|---|
| `id` | int, PK | |
| `session_id` | char(64), indexed | references `sessions.session_id` — **no formal FK constraint** in `install.xml`, application-level referential integrity only |
| `role` | char(16) | `"user"` or `"assistant"` |
| `content` | text | raw markdown, untranslated |
| `tokens_used` | int, nullable | defined but not currently populated by any code path (the Mistral SDK response's token-usage field is not read) |
| `created_at` | int | unix timestamp |

### `mdl_local_ai_system_message_translations`
*(ORM: `db/models/message_translation.py` → `MessageTranslationModel`)*

| Column | Type | Notes |
|---|---|---|
| `id` | int, PK | |
| `message_id` | int, indexed | references `messages.id` |
| `language` | char(5), indexed | |
| `content` | text | cached translated content |
| `created_at` | int | |

Unique constraint (both in SQLAlchemy `__table_args__` and in `install.xml`) on
`(message_id, language)` — enforces "at most one cached translation per message per
language," which `MessageTranslationRepository.create` relies on implicitly (it always
inserts, assuming `get()` was already checked first — a race between two concurrent
requests translating the same message into the same language for the first time could
violate this constraint and raise an integrity error, though this is a narrow edge case).

### `mdl_local_ai_system_logs`
Defined in `install.xml` (`user_id`, `session_id`, `event_type`, `provider`,
`latency_ms`, `error_message`, `created_at`) but has **no corresponding SQLAlchemy model
and no code path that writes to it** — appears to be a planned-but-not-yet-implemented
observability table.

## Referential integrity caveat

Deleting a session (`DELETE /sessions/{id}`) removes only the session row —
`SessionRepository.delete` does not cascade-delete rows in `messages` or
`message_translations` that reference that `session_id`/`message_id`. Since there is no
database-level foreign key enforcing the relationship either, deleted sessions will leave
orphaned rows behind. If this matters for storage/cleanliness, it should be addressed
either with an explicit cascade delete in `SessionRepository.delete` or a periodic cleanup
job.

## Read-only access to Moodle's own tables (`db/repositories/db_course_repository.py`)

`CourseRepository` is explicitly documented in its own docstring as **read-only** — the
Python backend never writes to any native `mdl_*` table; all writes to Moodle's own data
model are Moodle's/the PHP plugin's exclusive responsibility.

| Method | Query | Used by |
|---|---|---|
| `get_all_course_ids()` | `SELECT id FROM mdl_course WHERE id != 1` | `/rag/index-all` |
| `course_exists(course_id)` | `SELECT id FROM mdl_course WHERE id = :id` | `/rag/index/{id}` pre-check |
| `get_course_name(course_id)` | `SELECT fullname FROM mdl_course WHERE id = :id` | single-course name lookups |
| `get_course_names(course_ids)` | `SELECT id, fullname FROM mdl_course WHERE id IN (...)` | bulk lookup for global-session citation building — one query instead of N |
| `get_enrolled_course_ids(user_id)` | joins `mdl_user_enrolments` ⋈ `mdl_enrol`, filters `status = 0` on both (active enrolment/method) and excludes course id `1` | the enrollment safety boundary for global-session retrieval |

Course id `1` (Moodle's site-level "front page" pseudo-course) is explicitly excluded
everywhere a course list is built, since it isn't a real course with real content to
index or scope a chat to.

## `db/repositories/db_session_repository.py` — legacy/unused

`DbSessionRepository` duplicates what `chatbot/repositories/session_repository.py`
already does, is not imported by `dependencies.py` or anything else in the codebase, and
contains an invalid import (`from datetime import int`) that would raise `ImportError` if
anything ever tried to import it. Recommend deleting this file during cleanup, or, if it
represents an in-progress refactor, finishing and consolidating it with
`SessionRepository` rather than keeping two parallel implementations.
