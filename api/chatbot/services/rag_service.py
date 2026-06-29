import asyncio
from sqlalchemy.orm import Session as DBSession
from settings import Settings
from chatbot.repositories.rag_repository import RagRepository
from rag.loaders.course_indexer import CourseIndexer
from rag.ingestion import IngestionPipeline
from db.connection import SessionLocal
from db.repositories.db_course_repository import CourseRepository

class RagService:
    def __init__(self, rag_repo: RagRepository, course_repo: CourseRepository, settings: Settings):
        self.rag_repo = rag_repo
        self.settings = settings
        self.course_repo = course_repo

    async def index_course_background(self, course_id: int, pipeline: IngestionPipeline) -> dict:
        """
        Creates a dedicated database session independent of the HTTP request
        that initiated the indexing (the request has already completed by this point).
        """
        collection_name = f"course_{course_id}"
        db = SessionLocal()
        try:
            print(f"[RagService] Starting background indexing for course {course_id}")

            if self.rag_repo.collection_exists(collection_name):
                self.rag_repo.delete_collection(collection_name)
                print(f"[RagService] Cleared old collection data for: {collection_name}")

            indexer = CourseIndexer(
                db=db,
                moodledata_path=self.settings.MOODLEDATA_PATH,
                pipeline=pipeline
            )
            result = indexer.index_course(course_id, reset=False)
            return result

        except Exception as e:
            print(f"[RagService] Critical error indexing course {course_id}: {str(e)}")
            return {
                "course_id": course_id,
                "collection": collection_name,
                "documents": 0,
                "chunks": 0,
                "success": False,
                "error": str(e),
            }
        finally:
            db.close()
            
    def get_all_course_ids(self) -> list[int]:
        return self.course_repo.get_all_course_ids()
    
    async def index_all_courses_background(self, course_ids: list[int], pipeline: IngestionPipeline) -> list[dict]:
        """
        It reindexes all courses sequentially.
        It is intentionally *not* done in parallel—processing multiple courses simultaneously
        would cause them to compete for the same embedding model, GPU, or CPU,
        significantly slowing each other down; plus, progress logs are easier to read this way.
        """
        results = []
        for course_id in course_ids:
            result = await self.index_course_background(course_id, pipeline)
            results.append(result)
        return results
    