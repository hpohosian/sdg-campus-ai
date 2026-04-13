# api/chatbot/session_repository.py
from typing import Dict, List
from uuid import uuid4
from .schemas import ChatMessage

class Session:
    """Stores session information"""
    def __init__(self, session_id: str, user_id: int):
        self.id = session_id
        self.user_id = user_id
        self.messages: List[ChatMessage] = []

class SessionRepository:
    """The simplest session repository for MVP (in-memory)"""
    def __init__(self):
        # session_id -> Session
        self.sessions: Dict[str, Session] = {}

    async def get_or_create(self, session_id: str, user_id: int) -> Session:
        if session_id in self.sessions:
            return self.sessions[session_id]
        # create a new session
        session = Session(session_id=session_id, user_id=user_id)
        self.sessions[session_id] = session
        return session

    async def get_messages(self, session_id: str) -> List[ChatMessage]:
        session = self.sessions.get(session_id)
        if not session:
            return []
        return session.messages

    async def save_message(self, session_id: str, role: str, content: str) -> ChatMessage:
        session = self.sessions.get(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        message = ChatMessage(role=role, content=content)
        session.messages.append(message)
        return message
    