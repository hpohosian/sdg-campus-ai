from typing import Optional, List, Literal
from pydantic import BaseModel

class CreateSessionRequest(BaseModel):
    course_id: int | None = None
    title: str | None = None
    
class SessionResponse(BaseModel):
    session_id: str
    user_id: int
    course_id: int | None = None
    title: str | None = None

class UpdateSessionRequest(BaseModel):
    title: str | None = None
    
class SendMessageRequest(BaseModel):
    content: str
    
class MessageResponse(BaseModel):
    id: int
    session_id: str
    role: str
    content: str
    tokens_used: int | None = None
    created_at: int
    
