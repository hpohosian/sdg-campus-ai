from sqlalchemy.orm import Session as DBSession
from datetime import int
import time as t

from api.db.models.session import SessionModel


class DbSessionRepository:
    def __init__(self, db: DBSession):
        self.db = db

    async def create(self, session_data):
        db_session = SessionModel(
            session_id=session_data.session_id,
            userid=session_data.user_id,
            courseid=session_data.course_id,
            title=session_data.title,
            created_at=int(t.time()),
            updated_at=int(t.time()),
            is_active=1
        )

        self.db.add(db_session)
        self.db.commit()
        self.db.refresh(db_session)

        return db_session
