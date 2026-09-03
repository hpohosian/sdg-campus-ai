from sqlalchemy import Column, Integer, String, Text
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class MessageModel(Base):
    __tablename__ = "mdl_local_ai_system_messages"

    id = Column(Integer, primary_key=True, index=True)

    session_id = Column(String(64), nullable=False, index=True)

    role = Column(String(16), nullable=False)

    content = Column(Text, nullable=False)

    # --- Versioning (edit / regenerate) ---
    # Every message points at the message it directly follows in the
    # conversation. NULL means "first message of the session". Editing a
    # user message or regenerating an assistant reply never deletes or
    # mutates the original row -- it inserts a new SIBLING under the same
    # parent_id and flips is_active. Older siblings stay in the DB
    # (is_active=0) so switching back to them is just flipping the flag
    # again, no data loss. The live conversation is reconstructed by
    # walking from the active root and following each node's active
    # child (see MessageRepository.get_active_thread).
    parent_id = Column(Integer, nullable=True, index=True)
    is_active = Column(Integer, nullable=False, default=1)

    # Relative path (e.g. "session123/9f2c1a.jpg") under CHAT_IMAGES_DIR.
    # NEVER an absolute filesystem path — that breaks the moment the
    # storage root moves (different machine, container, etc). Nullable:
    # most messages have no attached image.
    image_path = Column(String(500), nullable=True)

    tokens_used = Column(Integer, nullable=True)

    created_at = Column(Integer, nullable=False)
