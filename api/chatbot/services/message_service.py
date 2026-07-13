from chatbot.repositories.message_repository import MessageRepository
from chatbot.repositories.session_repository import SessionRepository
from chatbot.repositories.message_translation_repository import MessageTranslationRepository  # NEW
from db.repositories.db_course_repository import CourseRepository
from chatbot.course_links import format_course_link, build_course_links

from chatbot.services.ai_service import AIService
from translation.translator import Translator  # NEW

from chatbot.schemas import MessageResponse


class MessageService:
    def __init__(
        self,
        message_repo: MessageRepository,
        session_repo: SessionRepository,
        ai_service: AIService,
        course_repo: CourseRepository,
        translation_repo: MessageTranslationRepository,
        translator: Translator,
    ):
        self.message_repo = message_repo
        self.session_repo = session_repo
        self.ai_service = ai_service
        self.course_repo = course_repo
        self.translation_repo = translation_repo
        self.translator = translator

    # =========================
    # GET SESSION MESSAGES 
    # =========================
    async def get_session_messages(self, session_id: str):
        messages = self.message_repo.get_by_session(session_id)
        return messages

    # =========================
    # GET SESSION MESSAGES FOR DISPLAY 
    # =========================
    async def get_session_messages_for_display(self, session_id: str):
        session = self.session_repo.get(session_id)
        if not session:
            raise ValueError("Session not found")

        messages = self.message_repo.get_by_session(session_id)

        return [
            MessageResponse(
                id=m.id,
                session_id=m.session_id,
                role=m.role,
                content=await self._translate_message(m, session.language),
                tokens_used=m.tokens_used,
                created_at=m.created_at,
            )
            for m in messages
        ]

    # =========================
    # TRANSLATE ONE MESSAGE
    # =========================
    async def _translate_message(self, message, target_language: str | None) -> str:
        if not target_language:
            return message.content

        cached = self.translation_repo.get(message.id, target_language)
        if cached:
            return cached.content

        translated = await self.translator.translate(message.content, target_language)
        self.translation_repo.create(message.id, target_language, translated)
        return translated

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
            tokens_used=tokens_used,
        )

    def _resolve_search_scope(self, session) -> tuple[str | None, list[int] | None, list[int]]:
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

        existing_messages = await self.get_session_messages(session_id)
        is_first_message = len(existing_messages) == 0

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

        generated_title = None
        if is_first_message and session.title == "New Chat":
            generated_title = await self.ai_service.generate_title(content, ai_text)
            self.session_repo.update(session_id, title=generated_title)

        user_display = await self._translate_message(user_message, session.language)
        assistant_display = await self._translate_message(assistant_message, session.language)

        return {
            "user": MessageResponse(
                id=user_message.id, session_id=user_message.session_id, role=user_message.role,
                content=user_display, tokens_used=user_message.tokens_used, created_at=user_message.created_at,
            ),
            "assistant": MessageResponse(
                id=assistant_message.id, session_id=assistant_message.session_id, role=assistant_message.role,
                content=assistant_display, tokens_used=assistant_message.tokens_used, created_at=assistant_message.created_at,
            ),
            "title": generated_title,
        }

    # =========================
    # STREAM RESPONSE
    # =========================
    async def chat_stream(self, session_id: str, content: str):
        session = self.session_repo.get(session_id)
        if not session:
            raise ValueError("Session not found")

        existing_messages = await self.get_session_messages(session_id)
        is_first_message = len(existing_messages) == 0                # NEW

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

        if is_first_message and session.title == "New Chat":           # NEW
            generated_title = await self.ai_service.generate_title(content, full_response)
            self.session_repo.update(session_id, title=generated_title)
            

    def _build_course_link_context(self, session, collection_name, relevant_course_ids):
        if not relevant_course_ids:
            return None, None

        course_names = self.course_repo.get_course_names(relevant_course_ids)
        links = build_course_links(course_names)

        if collection_name:
            return links.get(session.course_id), None
        return None, links
    
    