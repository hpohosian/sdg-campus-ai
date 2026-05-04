from sqlalchemy.orm import Session as DBSession
from db.models.session import SessionModel
import time
from sqlalchemy import select


# -------------------------
# Domain model (можно оставить, но не обязателен здесь)
# -------------------------
class Session:
    def __init__(
        self,
        session_id: str,
        user_id: int,
        course_id: int | None = None,
        title: str | None = None,
    ):
        self.id = session_id
        self.user_id = user_id
        self.course_id = course_id
        self.title = title


# -------------------------
# Repository (DB layer)
# -------------------------
class SessionRepository:
    def __init__(self, db: DBSession):
        self.db = db

    def create(self, session: Session) -> SessionModel:
        """
        Creates an entry in Moodle DB
        """

        db_session = SessionModel(
            session_id=session.id,
            user_id=session.user_id,
            course_id=session.course_id,
            title=session.title,
            created_at=int(time.time()),
            updated_at=int(time.time()),
            is_active=1
        )

        # Save in DB
        self.db.add(db_session)
        self.db.commit()
        self.db.refresh(db_session)

        return db_session
    
    def get(self, session_id: str):
        result = self.db.execute(
            select(SessionModel).where(SessionModel.session_id == session_id)
        )
        return result.scalar_one_or_none()
    
    def get_by_user(self, user_id: int):
        result = self.db.execute(
            select(SessionModel).where(SessionModel.user_id == user_id)
        )
        return result.scalars().all()
    
    def update(self, session_id: str, title: str | None = None):
        db_session = self.get(session_id)

        if not db_session:
            return None

        if title is not None:
            db_session.title = title

        db_session.updated_at = int(time.time())

        self.db.commit()
        self.db.refresh(db_session)

        return db_session

    def set_active(self, session_id: str, is_active: int):
        session = self.get(session_id)

        if not session:
            return None

        session.is_active = is_active
        self.db.commit()
        self.db.refresh(session)
        return session
    
    def delete(self, session_id: str):
        session = self.get(session_id)

        if not session:
            return None

        self.db.delete(session)
        self.db.commit()
        return True
