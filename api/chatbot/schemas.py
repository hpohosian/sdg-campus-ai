from typing import Optional, List, Literal
from pydantic import BaseModel

class ChatRequest(BaseModel):
    session_id: str       # unique session identifier
    user_id: int          # Moodle user ID
    message: str
    course_id: Optional[int] = None

class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str

class ChatResponse(BaseModel):
    session_id: str
    message: str
    # message_id: str
    