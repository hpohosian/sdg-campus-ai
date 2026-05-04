from uuid import uuid4
from chatbot.repositories.session_repository import SessionRepository, Session


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
        db_session = self.session_repo.create(session)

        # 4. return response (NOT domain object)        
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
    ):
        session = self.session_repo.update(
            session_id=session_id,
            title=title,
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
