from uuid import uuid4
from chatbot.repositories.session_repository import SessionRepository, Session, _UNSET


class SessionService:
    def __init__(self, session_repo: SessionRepository):
        self.session_repo = session_repo


    # =========================
    # CREATE
    # =========================
    async def create_session(
        self,
        user_id: int,
        course_id: int | None = None,
        title: str | None = None,
    ):
        session_id = str(uuid4())

        session = Session(
            session_id=session_id,
            user_id=user_id,
            course_id=course_id,
            title=title,
        )

        db_session = self.session_repo.create(session)
        return db_session


    # =========================
    # GET ONE
    # =========================
    async def get_session(self, session_id: str):
        session = self.session_repo.get(session_id)

        if not session:
            raise ValueError(f"Session {session_id} not found")

        return session


    # =========================
    # GET USER SESSIONS
    # =========================
    async def get_user_sessions(self, user_id: int):
        sessions = self.session_repo.get_by_user(user_id)
        return sessions


    # =========================
    # UPDATE
    # =========================
    async def update_session(
        self,
        session_id: str,
        title: str | None = None,
        language=_UNSET,
    ):
        session = self.session_repo.update(
            session_id=session_id,
            title=title,
            language=language,
        )

        if not session:
            raise ValueError("Session not found")

        return session


    # =========================
    # ARCHIVE SESSION (soft delete)
    # =========================
    async def archive_session(self, session_id: str):
        session = self.session_repo.set_active(session_id, 0)

        if not session:
            raise ValueError("Session not found")

        return session


    # =========================
    # DEARCHIVE SESSION
    # =========================
    async def dearchive_session(self, session_id: str):
        session = self.session_repo.set_active(session_id, 1)

        if not session:
            raise ValueError("Session not found")

        return session


    # =========================
    # DELETE
    # =========================
    async def delete_session(self, session_id: str):
        result = self.session_repo.delete(session_id)

        if not result:
            raise ValueError("Session not found")

        return result
