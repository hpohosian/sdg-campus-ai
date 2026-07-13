from chatbot.repositories.message_repository import MessageRepository
from chatbot.repositories.session_repository import SessionRepository
from db.repositories.db_course_repository import CourseRepository
from chatbot.course_links import format_course_link, build_course_links

from chatbot.services.ai_service import AIService

from chatbot.schemas import MessageResponse

# Позже здесь будут:
# validation
# permissions
# pagination
# token limits
# LLM orchestration

class MessageService:
    def __init__(
        self,
        message_repo: MessageRepository,
        session_repo: SessionRepository,
        ai_service: AIService,
        course_repo: CourseRepository,
    ):
        self.message_repo = message_repo
        self.session_repo = session_repo
        self.ai_service = ai_service
        self.course_repo = course_repo


    # =========================
    # GET SESSION MESSAGES
    # =========================
    async def get_session_messages(self, session_id: str):
        messages = self.message_repo.get_by_session(session_id)

        return messages
    
    
    # =========================
    # SAVE USER MESSAGE ONLY
    # =========================
    async def create_user_message(self, session_id: str, content: str):
        session = self.session_repo.get(session_id)

        if not session:
            raise ValueError("Session not found")

        return self.message_repo.create(
            session_id=session_id,
            role="user",
            content=content,
        )
        
    
    # =========================
    # SAVE ASSISTANT MESSAGE ONLY
    # =========================
    async def create_assistant_message(self, session_id: str, content: str, tokens_used: int | None = None):
        session = self.session_repo.get(session_id)
        
        if not session:
            raise ValueError("Session not found")
        
        return self.message_repo.create(
            session_id=session_id,
            role="assistant",
            content=content,
        )
        
    
    def _resolve_search_scope(self, session) -> tuple[str | None, list[int] | None, list[int]]:
        """
        Decides what to search:
        - a specific course (collection_name) if the session is tied to one course
        - otherwise, all of the user's enrolled courses (course_ids) as a global fallback

        Also returns `relevant_course_ids` — the course id(s) actually in
        scope either way — so callers can look up course names/links
        without caring which branch was taken.
        """
        if session.course_id:
            return f"course_{session.course_id}", None, [session.course_id]

        course_ids = self.course_repo.get_enrolled_course_ids(session.user_id)

        print(f"[scope] global mode: user_id={session.user_id}, enrolled course_ids={course_ids}")

        return None, (course_ids or None), (course_ids or [])
    
        
    # =========================
    # GENERATE FULL RESPONSE
    # =========================
    async def chat(self, session_id: str, content: str):
        session = self.session_repo.get(session_id)
        if not session:
            raise ValueError("Session not found")

        collection_name, course_ids, relevant_course_ids = self._resolve_search_scope(session)
        course_link, course_links = self._build_course_link_context(
            session, collection_name, relevant_course_ids
        )

        user_message = await self.create_user_message(session_id, content)
        history = await self.get_session_messages(session_id)
        ai_text = await self.ai_service.generate_response(
            history,
            collection_name=collection_name,
            course_ids=course_ids,
            course_link=course_link,
            course_links=course_links,
        )
        assistant_message = await self.create_assistant_message(session_id, ai_text)
        return {
            "user": MessageResponse.from_orm(user_message),
            "assistant": MessageResponse.from_orm(assistant_message)
        }
        
    
    # =========================
    # STREAM RESPONSE
    # =========================
    async def chat_stream(self, session_id: str, content: str):
        session = self.session_repo.get(session_id)
        if not session:
            raise ValueError("Session not found")

        collection_name, course_ids, relevant_course_ids = self._resolve_search_scope(session)
        course_link, course_links = self._build_course_link_context(
            session, collection_name, relevant_course_ids
        )

        await self.create_user_message(session_id, content)

        raw_history = await self.get_session_messages(session_id)
        history = [{"role": msg.role, "content": msg.content} for msg in raw_history]

        full_response = ""
        async for token in self.ai_service.stream_response(
            history,
            collection_name=collection_name,
            course_ids=course_ids,
            course_link=course_link,
            course_links=course_links,
        ):
            full_response += token
            yield token

        await self.create_assistant_message(session_id, full_response)

    def _build_course_link_context(
        self,
        session,
        collection_name: str | None,
        relevant_course_ids: list[int],
    ) -> tuple[str | None, dict[int, str] | None]:
        """
        Looks up course name(s) for whatever is in scope and builds
        ready-to-use markdown link(s), so the LLM only ever copies a
        citation instead of constructing a URL itself.

        Returns (course_link, course_links):
          - course_link: a single markdown link string, used when a
            specific course is selected (collection_name mode)
          - course_links: {course_id: markdown_link}, used in global
            (multi-course) search mode
        Exactly one of the two will be non-None, matching whichever
        mode _resolve_search_scope picked.
        """
        if not relevant_course_ids:
            return None, None

        course_names = self.course_repo.get_course_names(relevant_course_ids)
        links = build_course_links(course_names)

        if collection_name:
            return links.get(session.course_id), None
        return None, links
    