from sqlalchemy.orm import Session as DBSession
from sqlalchemy import select
from db.models.message import MessageModel
import time

# -------------------------
# Domain model
# -------------------------
# class Message:
#     def __init__(
#         self,
#         session_id: str,
#         role: int,
#         content: int | None = None,
#         tokens_used: str | None = None,
#     ):
#         self.id = session_id
#         self.role = role
#         self.content = content
#         self.tokens_used = tokens_used
        
        
# -------------------------
# Repository (DB layer)
# -------------------------
class MessageRepository:
    def __init__(self, db: DBSession):
        self.db = db


    # =========================
    # GET SESSION MESSAGES
    # =========================
    def get_by_session(self, session_id: str):
        result = self.db.execute(
            select(MessageModel)
            .where(MessageModel.session_id == session_id)
            .order_by(MessageModel.created_at.asc())
        )

        return result.scalars().all()
    
    
    # =========================
    # CREATE MESSAGE
    # =========================
    def create(self, session_id: str, role: str, content: str):
        message = MessageModel(
            session_id=session_id,
            role=role,
            content=content,
            created_at=int(time.time()),
            tokens_used=None
        )

        self.db.add(message)
        self.db.commit()
        self.db.refresh(message)

        return message
    