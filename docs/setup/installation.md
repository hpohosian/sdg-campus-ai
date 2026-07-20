# Installation & Local Setup

This assumes a working local Moodle installation already exists (the project was
developed against a Windows Moodle install using the official
`MoodleWindowsInstaller`, per the default paths in `settings.py`) and that you're setting
up the Python backend + plugin alongside it.

## 1. Backend (`api/`)

### 1.1 Python environment

The repository does not currently commit a `requirements.txt`. Until one is added, the
known-working dependency set (extracted from the project's own `.venv`) is:

```bash
cd api
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate

pip install fastapi "uvicorn[standard]" pydantic pydantic-settings python-dotenv \
            sqlalchemy pymysql mistralai \
            chromadb sentence-transformers torch transformers tokenizers \
            huggingface-hub scikit-learn numpy pymupdf beautifulsoup4
```

> Recommended follow-up: once dependencies are confirmed working,
> `pip freeze > requirements.txt` and commit it, so the environment is reproducible
> without needing to inspect an installed `.venv`.

### 1.2 Environment variables

Create `api/.env` (this is the actual working configuration used during development —
adjust paths/secrets for your machine):

```dotenv
MISTRAL_API_KEY=your-mistral-api-key
MISTRAL_MODEL=mistral-large-latest

MOODLE_SECRET=choose-a-long-random-secret

LOG_LEVEL=INFO
ENVIRONMENT=development
DEBUG=true

DATABASE_URL=mysql+pymysql://username:password@localhost:3307/moodle

EMBEDDING_MODEL=paraphrase-multilingual-mpnet-base-v2
HF_HOME=/path/to/huggingface_cache
HF_HUB_DISABLE_XET=1

MOODLEDATA_PATH=/path/to/moodledata

INTERNAL_API_KEY=choose-a-second-long-random-secret

MOODLE_BASE_URL=http://127.0.0.1
```

Notes:
- `DATABASE_URL` must point at the **same MySQL database Moodle itself uses** — this
  backend adds its own tables into Moodle's database rather than using a separate one.
- `MOODLEDATA_PATH` must be the real path to Moodle's `moodledata` directory (where
  uploaded course files, including PDFs, actually live on disk) — get this from Moodle's
  own `config.php` (`$CFG->dataroot`) if unsure.
- `MOODLE_BASE_URL` must have **no trailing slash** — it's used directly in string
  concatenation to build course/file links (`course_links.py`, `pdf_loader.py`).
- `MOODLE_SECRET` and `INTERNAL_API_KEY` must exactly match the `api_secret` and
  `internal_api_key` values entered on the Moodle plugin's settings page (step 2.3) — a
  mismatch here causes every signed request to fail with `401`.
- First run will download the `EMBEDDING_MODEL` from HuggingFace Hub into `HF_HOME` (a
  few hundred MB) — make sure the machine has network access the first time, or
  pre-populate the cache.

### 1.3 Run the API

```bash
cd api
uvicorn main:app --reload --port 8001
```

Watch the console for `Loading embedding model: ...` / `Embedding model loaded.` — this
happens once, on the first request that touches the RAG dependency chain (not
necessarily at startup, since it's wired through FastAPI's `Depends()` system rather than
an explicit startup hook).

Visit `http://127.0.0.1:8001/docs` for FastAPI's auto-generated interactive API
documentation (Swagger UI) — useful for testing endpoints directly (with Postman or the
`/docs` UI) before wiring up the Moodle plugin, using an `X-User-Id` header for
authenticated endpoints as described in [backend/overview.md](../backend/overview.md).

## 2. Moodle plugin

### 2.1 Install the plugin

Copy (or symlink) `moodle-plugin/local/ai_system` into your Moodle installation's
`local/` directory, so the path becomes `<moodle-root>/local/ai_system/`.

Then visit Site administration → Notifications in the Moodle admin UI (or run
`php admin/cli/upgrade.php` from the Moodle root) to trigger the plugin installer, which
reads `db/install.xml` and creates the plugin's 4 database tables.

### 2.2 Rebuild the AMD JavaScript (if you edit `amd/src/chatbot.js`)

Moodle serves the **compiled** `amd/build/chatbot.min.js`, not the source file directly.
After any change to `amd/src/chatbot.js`, rebuild it using Moodle's standard front-end
build tooling (from the Moodle root, with Node/npm set up per Moodle's own developer
docs):

```bash
grunt amd --root=local/ai_system
```

(Or the equivalent `npx grunt` invocation matching your Moodle version's build setup.)
Skipping this step means your JS edits will not appear in the browser.

### 2.3 Configure the plugin

Site administration → Plugins → Local plugins → AI System:

| Setting | Value |
|---|---|
| AI API base URL | `http://127.0.0.1:8001` (or wherever `uvicorn` is running) |
| Internal API key | must exactly match `INTERNAL_API_KEY` in `api/.env` |
| API secret | must exactly match `MOODLE_SECRET` in `api/.env` |

### 2.4 Grant capabilities

By default, `local_ai_system:use_chatbot` is granted to the `user`, `student`,
`teacher`, `editingteacher`, and `manager` archetypes (see `db/access.php`), so most
installations won't need to touch role permissions manually. If a custom role setup
doesn't include one of those archetypes, grant the capability explicitly via
Site administration → Users → Permissions → Define roles.

### 2.5 Verify the widget appears

Log in and visit the site's dashboard (`my-index`), the site front page
(`site-index`), or a course's main page (`course-index`) — these are the three page
types `lib.php`'s `local_ai_system_before_footer()` currently shows the floating button
on. Click the button; it should load `local/ai_system/index.php?embed=1` inside the slide-in
panel.

## 3. Index course content for RAG

Retrieval only works once a course has been indexed into ChromaDB.

- **Automatic**: editing a course (creating/updating it, adding/editing/removing an
  activity, updating a section) automatically queues a reindex task, which runs on
  Moodle's next cron tick. Make sure Moodle's cron is actually running
  (`php admin/cli/cron.php` on a schedule, or Moodle's built-in cron-via-web if
  configured) — without cron running, queued reindex tasks never execute.
- **Manual, one course**: `POST http://127.0.0.1:8001/rag/index/{course_id}` with header
  `X-Internal-Api-Key: <your INTERNAL_API_KEY>` and body `{"reset": true}`.
- **Manual, all courses**: `POST http://127.0.0.1:8001/rag/index-all` with the same
  header, no body needed.
- **Check status**: `GET http://127.0.0.1:8001/rag/status/{course_id}` — no auth
  required, reports chunk/document counts once indexing has finished.

Indexing runs as a FastAPI background task, so the POST request returns immediately
(`202 Accepted`); poll the status endpoint to know when it's actually done. Progress and
per-file logs (`[indexer] ...`, `[pdf_loader] ...`, `[moodle_loader] ...`) print to the
`uvicorn` console.

## 4. Common pitfalls

| Symptom | Likely cause |
|---|---|
| Every request from Moodle gets `401 Invalid signature` | `api_secret` (Moodle) and `MOODLE_SECRET` (`.env`) don't match |
| `/rag/index/*` returns `401 Missing internal API key` | `internal_api_key` (Moodle) and `INTERNAL_API_KEY` (`.env`) don't match |
| Chat answers never cite course material / feel generic | course hasn't been indexed yet — check `/rag/status/{course_id}` |
| PDFs skipped during indexing (`"Skipped (no text)"` in logs) | scanned/image-only PDF with no extractable text layer — there is no OCR fallback |
| Course links / PDF citation links point to the wrong host | `MOODLE_BASE_URL` in `.env` doesn't match Moodle's real address, or has a trailing slash |
| Streaming works from `/docs` but not from the Moodle widget | check `ajax/stream.php`'s hard-coded `$base_url` matches where `uvicorn` is actually listening |
| First message after server start is very slow | expected — the embedding model is loading for the first time (~1-2s+, longer on first-ever run while it downloads) |
