from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException, status
from sqlalchemy.orm import Session as DBSession

from db.repositories.db_course_repository import CourseRepository
from db.connection import get_db
from dependencies import get_settings, get_vector_store, get_embedding_model
from settings import Settings
from rag.ingestion import IngestionPipeline

from chatbot.schemas import IndexAllResponse, IndexCourseRequest, RagStatusResponse
from chatbot.repositories.rag_repository import RagRepository
from chatbot.services.rag_service import RagService

router = APIRouter(prefix="/rag", tags=["rag"])

from middleware.internal_auth import verify_internal_api_key

from dependencies import get_settings, get_vector_store, get_embedding_model, get_course_repository


# -------------------------
# Dependency Injections
# -------------------------
def get_rag_repository(vector_store = Depends(get_vector_store)) -> RagRepository:
    return RagRepository(vector_store)

def get_rag_service(
    repo: RagRepository = Depends(get_rag_repository),
    course_repo: CourseRepository = Depends(get_course_repository),
    settings: Settings = Depends(get_settings),
) -> RagService:
    return RagService(repo, course_repo, settings)


# =========================
# TRIGGER COURSE INDEXING
# =========================
@router.post(
    "/index/{course_id}", 
    status_code=status.HTTP_202_ACCEPTED,
    response_model=RagStatusResponse,
    dependencies=[Depends(verify_internal_api_key)]
)
async def index_course(
    course_id: int,
    request: IndexCourseRequest,
    background_tasks: BackgroundTasks,
    service: RagService = Depends(get_rag_service),
    course_repo: CourseRepository = Depends(get_course_repository),
    embed_model = Depends(get_embedding_model),
    v_store = Depends(get_vector_store),
):
    if not course_repo.course_exists(course_id):
        raise HTTPException(status_code=404, detail=f"Course {course_id} not found")

    pipeline = IngestionPipeline(embedding_model=embed_model, vector_store=v_store)

    background_tasks.add_task(
        service.index_course_background,
        course_id=course_id,
        pipeline=pipeline,
    )

    return RagStatusResponse(
        course_id=course_id,
        collection_name=f"course_{course_id}",
        success=True,
        message="Course indexing pipeline successfully pushed to background worker.",
    )
    

@router.get("/status/{course_id}", response_model=RagStatusResponse)
def get_status(course_id: int, v_store = Depends(get_vector_store)):
    collection_name = f"course_{course_id}"

    if not v_store.collection_exists(collection_name):
        return RagStatusResponse(
            course_id=course_id,
            collection_name=collection_name,
            success=False,
            message="Collection does not exist"
        )

    collection = v_store.client.get_collection(collection_name)
    count = collection.count()

    all_meta = collection.get(include=["metadatas"])["metadatas"]
    unique_sources = {m.get("source_name") for m in all_meta if m.get("source_name")}

    return RagStatusResponse(
        course_id=course_id,
        collection_name=collection_name,
        documents_indexed=len(unique_sources),
        chunks_indexed=count,
        success=True,
        message="OK"
    )
    
    
@router.post(
    "/index-all", 
    status_code=status.HTTP_202_ACCEPTED, 
    response_model=IndexAllResponse,
    dependencies=[Depends(verify_internal_api_key)]
)
async def index_all_courses(
    background_tasks: BackgroundTasks,
    service: RagService = Depends(get_rag_service),
    embed_model = Depends(get_embedding_model),
    v_store = Depends(get_vector_store),
):
    course_ids = service.get_all_course_ids()
    pipeline = IngestionPipeline(embedding_model=embed_model, vector_store=v_store)

    background_tasks.add_task(
        service.index_all_courses_background,
        course_ids=course_ids,
        pipeline=pipeline,
    )

    return IndexAllResponse(
        total_courses=len(course_ids),
        message=f"Indexing pipeline started for {len(course_ids)} courses.",
    )