from sqlalchemy import BigInteger, Column, Integer, String

from db.base import Base


class SessionModel(Base):
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True)
    session_id = Column(String(64), unique=True, index=True, nullable=False)

    user_id = Column(Integer, nullable=False, index=True)
    course_id = Column(Integer, nullable=True)

    title = Column(String(255), nullable=True)
    language = Column(String(5), nullable=True, default=None)

    # Unix timestamps in seconds. BigInteger on purpose: a 32-bit INTEGER
    # overflows in January 2038.
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)

    is_active = Column(Integer, nullable=False, default=1)
