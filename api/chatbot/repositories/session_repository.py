from sqlalchemy.orm import Session as DBSession
from db.models.session import SessionModel
import time


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

    async def create(self, session: Session) -> SessionModel:
        """
        Creates an entry in Moodle DB
        """

        db_session = SessionModel(
            session_id=session.id,
            userid=session.user_id,
            courseid=session.course_id,
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
