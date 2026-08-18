from pydantic import BaseModel, ConfigDict


class CreateSessionRequest(BaseModel):
    course_id: int | None = None
    title: str | None = None


class SessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    session_id: str
    user_id: int
    course_id: int | None = None
    title: str | None = None
    language: str | None = None
    is_active: int


class UpdateSessionRequest(BaseModel):
    title: str | None = None
    language: str | None = None


class SendMessageRequest(BaseModel):
    content: str = ""
    image_base64: str | None = None
    image_mime_type: str | None = None


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: str
    role: str
    content: str
    image_url: str | None = None
    tokens_used: int | None = None
    created_at: int


class IndexCourseRequest(BaseModel):
    reset: bool = True


class RagStatusResponse(BaseModel):
    course_id: int
    collection_name: str
    documents_indexed: int = 0
    chunks_indexed: int = 0
    success: bool
    message: str | None = None


class IndexAllResponse(BaseModel):
    total_courses: int
    message: str
    
