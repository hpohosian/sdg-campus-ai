from uuid import uuid4
from chatbot.repositories.session_repository import SessionRepository, Session


class SessionService:
    def __init__(self, session_repo: SessionRepository):
        self.session_repo = session_repo

    async def create_session(
        self,
        user_id: int,
        course_id: int | None = None,
        title: str | None = None,
    ):
        # 1. generate session id
        session_id = str(uuid4())

        # 2. create domain object
        session = Session(
            session_id=session_id,
            user_id=user_id,
            course_id=course_id,
            title=title,
        )

        # 3. save to DB (IMPORTANT: get result back)
        db_session = await self.session_repo.create(session)

        # 4. return response (NOT domain object)
        return {
            "session_id": db_session.session_id,
            "user_id": db_session.userid,
            "course_id": db_session.courseid,
            "title": db_session.title,
            "is_active": db_session.is_active,
            "created_at": db_session.created_at,
        }
