from sqlalchemy import BigInteger, Column, Integer, String, Text, UniqueConstraint

from db.base import Base


class MessageTranslationModel(Base):
    __tablename__ = "message_translations"

    id = Column(Integer, primary_key=True)

    message_id = Column(Integer, nullable=False, index=True)
    language = Column(String(5), nullable=False, index=True)
    content = Column(Text, nullable=False)

    created_at = Column(BigInteger, nullable=False)

    __table_args__ = (
        UniqueConstraint("message_id", "language", name="uq_message_language"),
    )
