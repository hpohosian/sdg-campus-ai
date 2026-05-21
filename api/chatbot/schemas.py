# from typing import Optional, List, Literal
from pydantic import BaseModel
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
    is_active: int

class UpdateSessionRequest(BaseModel):
    title: str | None = None
    
class SendMessageRequest(BaseModel):
    content: str
    
class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    session_id: str
    role: str
    content: str
    tokens_used: int | None = None
    created_at: int
    
