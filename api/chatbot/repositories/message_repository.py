from sqlalchemy.orm import Session as DBSession
from sqlalchemy import select
from db.models.message import MessageModel
import time


class MessageRepository:
    def __init__(self, db: DBSession):
        self.db = db

    def get(self, message_id: int):
        result = self.db.execute(
            select(MessageModel).where(MessageModel.id == message_id)
        )
        return result.scalar_one_or_none()

    def get_by_session(self, session_id: str):
        result = self.db.execute(
            select(MessageModel)
            .where(MessageModel.session_id == session_id)
            .order_by(MessageModel.created_at.asc())
        )
        return result.scalars().all()

    def create(
        self,
        session_id: str,
        role: str,
        content: str,
        tokens_used: int | None = None,
        image_path: str | None = None,
    ):
        message = MessageModel(
            session_id=session_id,
            role=role,
            content=content,
            created_at=int(time.time()),
            tokens_used=tokens_used,
            image_path=image_path,
        )

        self.db.add(message)
        self.db.commit()
        self.db.refresh(message)

        return message
    