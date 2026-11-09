"""
Re-index course materials into ChromaDB directly from the command line —
for development. Does the same as POST /rag/index/{course_id} (which only
accepts requests signed by Moodle), without HTTP.

Run from the api/ folder:

    python -m eval.reindex 8            # one course
    python -m eval.reindex 8 11 12      # several
    python -m eval.reindex --all        # every course in Moodle

Needs the Moodle database (DATABASE_URL) and MOODLEDATA_PATH from .env.
Restart uvicorn afterwards so the running server surely sees the new index.
"""

import argparse
import asyncio
import sys

from eval.run_eval import load_env_file


async def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass

    p = argparse.ArgumentParser(description="Re-index courses (development)")
    p.add_argument("course_ids", nargs="*", type=int)
    p.add_argument("--all", action="store_true", help="all courses in Moodle")
    args = p.parse_args()
    if not args.course_ids and not args.all:
        p.error("give course ids (e.g. 8 11) or --all")

    load_env_file()
    from settings import settings
    from db.connection import MoodleSessionLocal
    from db.repositories.db_course_repository import CourseRepository
    from chatbot.repositories.rag_repository import RagRepository
    from chatbot.services.rag_service import RagService
    from rag.embeddings import EmbeddingModel
    from rag.vector_store import VectorStore
    from rag.ingestion import IngestionPipeline

    embedding_model = EmbeddingModel()
    store = VectorStore(embedding_model=embedding_model)
    pipeline = IngestionPipeline(embedding_model=embedding_model, vector_store=store)

    db = MoodleSessionLocal()
    try:
        service = RagService(RagRepository(store), CourseRepository(db), settings)
        course_ids = service.get_all_course_ids() if args.all else args.course_ids
        print(f"Re-indexing courses: {course_ids}")
        for cid in course_ids:
            result = await service.index_course_background(cid, pipeline)
            ok = "OK" if result.get("success", True) else f"FAILED: {result.get('error')}"
            print(f"  course {cid}: {result.get('documents', '?')} documents, "
                  f"{result.get('chunks', '?')} chunks -> {ok}")
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
    