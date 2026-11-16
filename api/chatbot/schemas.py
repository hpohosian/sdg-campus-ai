from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


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
    created_at: int | None = None  # unix seconds; the sidebar date groups (Today / This week / ...) depend on it


class UpdateSessionRequest(BaseModel):
    title: str | None = None
    language: str | None = None
    course_id: int | None = None


class SendMessageRequest(BaseModel):
    content: str = ""
    image_base64: str | None = None
    image_mime_type: str | None = None


class EditMessageRequest(BaseModel):
    content: str


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: str
    role: str
    content: str
    image_url: str | None = None
    tokens_used: int | None = None
    created_at: int
    # True = `content` is still the original text; the client fetches the
    # translation separately (POST .../messages/{id}/translate) and swaps
    # it in, so a long chat appears at once and translates message by message.
    translation_pending: bool = False
    # "text" (markdown in `content`), "quiz_request" or "quiz". For the two
    # quiz types `content` is empty and the data is in `quiz` (see
    # chatbot/quiz/service.py: quiz_view / quiz_request_view).
    content_type: str = "text"
    quiz: dict | None = None


class CreateQuizRequest(BaseModel):
    scope: Literal["chat", "course"] = "course"
    count: int = 5
    topic: str | None = Field(default=None, max_length=300)
    # Language of the UI; empty = chat language / language of the chat.
    language: str | None = Field(default=None, max_length=5)


class QuizAnswerRequest(BaseModel):
    question_index: int = Field(ge=0)
    # Indexes of the chosen options (one for single choice).
    answer: list[int] = Field(min_length=1, max_length=10)


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
