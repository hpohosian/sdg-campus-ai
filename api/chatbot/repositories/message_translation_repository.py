from sqlalchemy.orm import Session as DBSession
from sqlalchemy import select
from db.models.message_translation import MessageTranslationModel
import time


class MessageTranslationRepository:
    def __init__(self, db: DBSession):
        self.db = db

    def get(self, message_id: int, language: str):
        result = self.db.execute(
            select(MessageTranslationModel).where(
                MessageTranslationModel.message_id == message_id,
                MessageTranslationModel.language == language,
            )
        )
        return result.scalar_one_or_none()

    def create(self, message_id: int, language: str, content: str):
        translation = MessageTranslationModel(
            message_id=message_id,
            language=language,
            content=content,
            created_at=int(time.time()),
        )
        self.db.add(translation)
        self.db.commit()
        self.db.refresh(translation)
        return translation
    