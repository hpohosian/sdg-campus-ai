# RAG Pipeline (`api/rag/`)

Retrieval-Augmented Generation grounds the assistant's answers in real Moodle course
content. The pipeline has two halves: **ingestion** (course content → ChromaDB) and
**retrieval** (user query → relevant chunks → prompt context).

## Loaders (`rag/loaders/`)

### `MoodleDBLoader` (`moodle_db_loader.py`)

Pulls text content directly out of Moodle's own database tables — no file parsing
involved. For a given `course_id`, loads four content types:

| Method | Source table(s) | Notes |
|---|---|---|
| `_load_sections` | `mdl_course_sections` | section `summary` field, ordered by section number |
| `_load_pages` | `mdl_page` joined to `mdl_course_modules`/`mdl_course_sections` | full Page-activity content, prefixed with the page's `name` |
| `_load_book_chapters` | `mdl_book` + `mdl_book_chapters` | joined and ordered by `pagenum`; text prefixed with `"{book_name} — {chapter_title}"` |
| `_load_labels` | `mdl_label` | label `intro` text blocks |

All HTML is stripped via `clean_html()` (BeautifulSoup `get_text(separator=" ")`, then
whitespace collapsed with a regex). Documents shorter than 50 characters after cleaning
are discarded (`load_course`'s final filter) — this removes near-empty sections/labels
that would otherwise pollute the vector store with low-value chunks.

Each returned document dict carries metadata: `course_id`, `source_type` (`section` /
`page` / `book_chapter` / `label`), `source_name`, `source` (used later for citation
labels), and `section`.

### `MoodlePDFLoader` (`pdf_loader.py`)

Handles PDF attachments, which Moodle stores as content-addressed blobs rather than in
its database.

1. `_get_course_pdf_files(course_id)` — queries `mdl_files` (mimetype
   `application/pdf`, non-empty, filename not `.`) joined to `mdl_context`, restricted to
   either course-module contexts (`contextlevel=70`) belonging to this course, or the
   course context itself (`contextlevel=50`).
2. `_get_file_path(contenthash)` — Moodle's storage layout is
   `moodledata/filedir/{hash[0:2]}/{hash[2:4]}/{hash}` — reconstructed here using
   `settings.MOODLEDATA_PATH`.
3. `_extract_pdf_text(contenthash)` — opens the file with PyMuPDF (`fitz`), concatenates
   `page.get_text()` across all pages. Files under 100 characters of extracted text are
   skipped (likely scanned/image-only PDFs with no extractable text layer — **note: there
   is no OCR fallback**, so scanned PDFs without a text layer will simply be silently
   skipped, logged as `"Skipped (no text)"`).
4. `_build_file_url(...)` — constructs a direct `pluginfile.php` download URL using the
   file's `contextid`/`component`/`filearea`/`itemid`/`filename`, stored in the chunk
   metadata as `file_url` — this is what lets the retriever produce a clickable citation
   straight to the original PDF (see `Retriever._format_source_label` below).

### `CourseIndexer` (`course_indexer.py`)

Orchestrates both loaders and the ingestion pipeline for one course:
`index_course(course_id, reset)` optionally deletes the existing `course_{id}` collection,
loads DB content + PDFs, combines them into one list, and calls
`IngestionPipeline.ingest_many()`. Returns a summary dict (`documents`, `chunks`,
`success`). `index_all_courses(course_ids, reset)` loops this per course.

## Chunking (`chunker.py`)

`TextChunker` — a structure-aware splitter, not a naive fixed-length cut:

1. **Split into paragraphs** on blank lines.
2. A paragraph that fits within `chunk_size` (default **1000 characters**) becomes one
   "unit" as-is.
3. An oversized paragraph is further split into **sentences** (regex on `.`/`!`/`?`
   followed by whitespace).
4. A single sentence still too long on its own gets a last-resort hard character-based
   cut — documented in code as something that "should be rare."
5. Units are then **greedily packed** into chunks up to `chunk_size`, never splitting a
   unit across a chunk boundary.
6. **Overlap** (default **150 characters**): when a chunk is closed, its trailing whole
   units (up to `chunk_overlap` characters worth) are carried forward as the start of the
   next chunk — so context isn't lost right at a chunk boundary, and the boundary itself
   still never lands mid-sentence.
7. Chunks under `min_chunk_size` (default **100 characters**) are discarded.

This design specifically exists to prevent a fact (a date, a named list, an author
citation) from being truncated exactly at a chunk edge, which was a real problem this
project ran into with a naive splitter — see the docstring in `chunker.py`.

## Embeddings (`embeddings.py`)

`EmbeddingModel` wraps `sentence_transformers.SentenceTransformer`, loaded **once** per
process (an expensive ~1-2 second operation) and reused for every subsequent call.

- Default model: `paraphrase-multilingual-mpnet-base-v2` (`EMBEDDING_MODEL` setting) — a
  multilingual model chosen so English, German, and other course-material languages all
  embed into a shared space, since SDG Campus content is not English-only.
- `embed_text(text)` — single string → `list[float]`, used for embedding the user's
  query at search time.
- `embed_chunks(chunks: list[Chunk])` — batch-encodes chunk text (`batch_size=32`, with a
  progress bar for batches over 10 items) and returns a list of
  `{"text", "embedding", "metadata", "chunk_index"}` dicts ready for storage.
- `embed_batch(texts)` — same batch path for raw strings without `Chunk` wrapping.

The `HF_HOME` and `HF_HUB_DISABLE_XET` environment variables are set at **import time**
of this module (before `sentence_transformers` is imported), so the HuggingFace cache
location must be correct in `.env` before the process starts — changing it at runtime
after the module has already been imported has no effect.

## Vector store (`vector_store.py`)

`VectorStore` wraps a ChromaDB `PersistentClient`, persisted to
`api/../../data/chromadb/` (i.e. `<repo-root>/data/chromadb/`), with
`anonymized_telemetry=False`. **One collection per course**, named `course_{course_id}`,
using cosine similarity (`hnsw:space: cosine`).

Key methods:
- `get_or_create_collection`, `list_collections`, `delete_collection`, `collection_exists`
- `add_embedded_chunks(collection_name, embedded_chunks)` — assigns a random UUID as each
  chunk's Chroma document id, stores `chunk_index` merged into the metadata dict.
- `search(collection_name, query, n_results, where=None)` — embeds the query text, guards
  against querying a nonexistent or empty collection (returns `[]` rather than raising),
  clamps `n_results` to the collection's actual `count()`, and converts ChromaDB's
  `distance` into a more intuitive `score = round(1 - distance, 4)` (higher = more
  similar), sorted descending.

## Retrieval (`retriever.py`)

`Retriever` sits between `VectorStore` and the LLM prompt.

- `retrieve(query, collection_name, n_results, min_score, where)` — calls
  `VectorStore.search` then filters out anything below `min_score` (**default 0.3**).
- `retrieve_as_context(...)` — formats filtered chunks into the citation-tagged blocks
  the system prompt expects:
  `"[Course: <link> — Source: <link-or-filename>]\n<chunk text>"`, joined with blank
  lines. Uses `_format_source_label` to prefer a clickable markdown link
  (`file_url` in metadata, set by `pdf_loader.py`) over a plain filename when available —
  DB-sourced content (pages, labels, etc.) has no `file_url`, so it degrades to a plain
  filename citation.
- `retrieve_global(query, course_ids, ...)` — the multi-course variant used for sessions
  not tied to a specific course. Searches each of the user's enrolled courses'
  collections independently, tags each result with its `course_id`, merges everything
  into one list, sorts by score descending, and returns only the top `n_results`
  **overall** (not top-N-per-course) — so a course with more/better-matching content can
  dominate the retrieved context for a given question, which is the intended behavior
  (most relevant material wins, regardless of which course it came from).
  - Has an optional `debug=True` mode that prints every candidate (before filtering/
    truncation) with its score, source, and keep/drop status — intended for local
    diagnosis of retrieval quality, explicitly documented as "leave this off in
    production."
- `retrieve_as_context_global(...)` — same formatting as `retrieve_as_context`, but
  resolves each result's `course_id` to a markdown link via the `course_links` dict
  passed in (falling back to a plain `f"Course {course_id}"` label if a lookup failed).
- `has_relevant_context(query, collection_name, min_score)` — a cheap boolean check
  (`n_results=1`) — defined but **not currently called anywhere** in the codebase; `
  AIService` makes its "use RAG or not" decision by checking whether
  `retrieve_as_context(...)` returned a non-empty string instead.

## Ingestion (`ingestion.py`)

`IngestionPipeline` glues the three pieces above together:

- `ingest_text(text, collection_name, metadata, source)` — chunk → embed → store, with
  per-document error handling (`IngestionResult(success=False, error=...)` rather than
  raising, so one bad document doesn't abort an entire course's indexing run).
- `ingest_file(file_path, collection_name, metadata)` — plain `.txt` file ingestion.
  **Not currently used by the Moodle-integrated pipeline** (`CourseIndexer` calls
  `ingest_many` with in-memory document dicts, not file paths) — this method exists for
  standalone/manual ingestion, e.g. from the `tests/` scripts.
- `ingest_many(documents, collection_name)` — the method actually used by
  `CourseIndexer`; loops `ingest_text` over a list of `{"text", "metadata", "source"}`
  dicts and logs an aggregate summary (`X/Y documents, Z total chunks`).

## Tuning knobs, in one place

| Parameter | Default | Where |
|---|---|---|
| `chunk_size` | 1000 chars | `TextChunker.__init__`, also `IngestionPipeline.__init__` |
| `chunk_overlap` | 150 chars | same |
| `min_chunk_size` | 100 chars | `TextChunker.__init__` |
| `min_score` (retrieval threshold) | 0.3 | `Retriever.__init__` |
| `n_results` (default retrieval count) | 5 | `Retriever.__init__`, but `AIService` always explicitly passes `n_results=8` |
| Embedding model | `paraphrase-multilingual-mpnet-base-v2` | `.env` `EMBEDDING_MODEL` |
| PDF min extracted length | 100 chars | `pdf_loader.py` `load_course_pdfs` |
| DB-sourced doc min length | 50 chars | `moodle_db_loader.py` `load_course` |
