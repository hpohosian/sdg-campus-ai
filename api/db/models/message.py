from sqlalchemy import Column, Integer, String, Text
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class MessageModel(Base):
    __tablename__ = "mdl_local_ai_system_messages"

    id = Column(Integer, primary_key=True, index=True)

    session_id = Column(String(64), nullable=False, index=True)

    role = Column(String(16), nullable=False)

    content = Column(Text, nullable=False)

    # Relative path (e.g. "session123/9f2c1a.jpg") under CHAT_IMAGES_DIR.
    # NEVER an absolute filesystem path — that breaks the moment the
    # storage root moves (different machine, container, etc). Nullable:
    # most messages have no attached image.
    image_path = Column(String(500), nullable=True)

    tokens_used = Column(Integer, nullable=True)

    created_at = Column(Integer, nullable=False)
