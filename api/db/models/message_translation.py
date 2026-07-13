from sqlalchemy import Column, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class MessageTranslationModel(Base):
    __tablename__ = "mdl_local_ai_system_message_translations"

    id = Column(Integer, primary_key=True, index=True)

    message_id = Column(Integer, nullable=False, index=True)
    language = Column(String(5), nullable=False, index=True)
    content = Column(Text, nullable=False)

    created_at = Column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("message_id", "language", name="uq_message_language"),
    )