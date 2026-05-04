from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class SessionModel(Base):
    __tablename__ = "mdl_local_ai_system_sessions"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(64), unique=True, index=True, nullable=False)

    userid = Column(Integer, nullable=False)
    courseid = Column(Integer, nullable=True)

    title = Column(String(255), nullable=True)

    created_at = Column(Integer, nullable=False)
    updated_at = Column(Integer, nullable=False)

    is_active = Column(Integer, nullable=False, default=1)
