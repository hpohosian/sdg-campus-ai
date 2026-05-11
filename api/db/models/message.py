from sqlalchemy import Column, Integer, String, Text
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class MessageModel(Base):
    __tablename__ = "mdl_local_ai_system_messages"

    id = Column(Integer, primary_key=True, index=True)

    session_id = Column(String(64), nullable=False, index=True)

    role = Column(String(16), nullable=False)

    content = Column(Text, nullable=False)

    tokens_used = Column(Integer, nullable=True)

    created_at = Column(Integer, nullable=False)
