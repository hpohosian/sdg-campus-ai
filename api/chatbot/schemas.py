from typing import Optional, List, Literal
from pydantic import BaseModel

class CreateSessionRequest(BaseModel):
    user_id: int
    course_id: int | None = None
    title: str | None = None
    
class SessionResponse(BaseModel):
    session_id: str
    user_id: int
    course_id: int | None = None
    title: str | None = None

