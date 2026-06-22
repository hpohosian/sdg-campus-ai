from sqlalchemy.orm import Session

from api.rag.loaders.moodle_db_loader import MoodleDBLoader
from api.rag.loaders.pdf_loader import MoodlePDFLoader
from api.rag.ingestion import IngestionPipeline


class CourseIndexer:
    """
    Indexes all content from a Moodle course into ChromaDB.
    
    Combines text content from DB and PDF files into a single
    collection per course: "course_{course_id}"
    """

    def __init__(
        self,
        db: Session,
        moodledata_path: str,
        pipeline: IngestionPipeline = None,
    ):
        self.db_loader = MoodleDBLoader(db)
        self.pdf_loader = MoodlePDFLoader(db, moodledata_path)
        self.pipeline = pipeline or IngestionPipeline()

    def index_course(self, course_id: int, reset: bool = False) -> dict:
        """
        Index all content for a course into ChromaDB.
        
        course_id: Moodle course ID
        reset: if True, delete existing collection first
        
        Returns summary dict with counts.
        """
        collection_name = f"course_{course_id}"

        if reset and self.pipeline.vector_store.collection_exists(collection_name):
            self.pipeline.vector_store.delete_collection(collection_name)
            print(f"[indexer] Deleted existing collection: {collection_name}")

        # Load from DB
        print(f"\n[indexer] Loading text content from DB...")
        db_docs = self.db_loader.load_course(course_id)

        # Load PDFs
        print(f"[indexer] Loading PDFs...")
        pdf_docs = self.pdf_loader.load_course_pdfs(course_id)

        all_docs = db_docs + pdf_docs
        print(f"[indexer] Total documents: {len(all_docs)}")

        if not all_docs:
            return {
                "course_id": course_id,
                "collection": collection_name,
                "documents": 0,
                "chunks": 0,
                "success": False,
                "error": "No content found",
            }

        # Ingest everything
        results = self.pipeline.ingest_many(all_docs, collection_name)

        total_chunks = sum(r.chunks_added for r in results)
        success_count = sum(1 for r in results if r.success)

        print(f"\n[indexer] Course {course_id} indexed:")
        print(f"  Documents: {success_count}/{len(all_docs)}")
        print(f"  Chunks: {total_chunks}")
        print(f"  Collection: {collection_name}")

        return {
            "course_id": course_id,
            "collection": collection_name,
            "documents": success_count,
            "chunks": total_chunks,
            "success": True,
        }

    def index_all_courses(self, course_ids: list[int], reset: bool = False) -> list[dict]:
        """Index multiple courses at once."""
        results = []
        for course_id in course_ids:
            print(f"\n{'='*50}")
            print(f"Indexing course {course_id}...")
            result = self.index_course(course_id, reset=reset)
            results.append(result)

        print(f"\n{'='*50}")
        print(f"Done! Indexed {len(results)} courses")
        return results