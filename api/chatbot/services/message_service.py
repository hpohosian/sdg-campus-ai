import asyncio

from chatbot.repositories.message_repository import MessageRepository
from chatbot.repositories.session_repository import SessionRepository
from chatbot.repositories.message_translation_repository import MessageTranslationRepository  # NEW
from chatbot.course_links import format_course_link, build_course_links

from chatbot.services.ai_service import AIService
from translation.translator import Translator  # NEW
from settings import settings

from chatbot.schemas import MessageResponse

from chatbot.services.image_storage import ImageStorage


# How many translation LLM calls may run at the same time when a session
# is opened in a language that hasn't been translated yet.
_TRANSLATION_CONCURRENCY = 12

# Sessions whose running answer the user has just stopped (the browser's "Stop"
# report arrived while the backend was still generating). The generating
# request checks this after every token and stops. The backend runs as ONE
# uvicorn process, so a module-level set is enough; with several workers this
# would have to move to the database or Redis.
_STOP_REQUESTED: set[str] = set()


class MessageService:
    def __init__(
        self,
        message_repo: MessageRepository,
        session_repo: SessionRepository,
        ai_service: AIService,
        enrolled_courses: dict[int, str],
        translation_repo: MessageTranslationRepository,
        translator: Translator,
        image_storage: ImageStorage,
    ):
        self.message_repo = message_repo
        self.session_repo = session_repo
        self.ai_service = ai_service
        # {course_id: full name} of the courses the user is enrolled in, as
        # stated by Moodle in the signed request (see middleware/auth.py).
        # The backend no longer asks Moodle's database for this.
        self.enrolled_courses = enrolled_courses
        self.translation_repo = translation_repo
        self.translator = translator
        self.image_storage = image_storage

    # =========================
    # GET SESSION MESSAGES 
    # =========================
    async def get_session_messages(self, session_id: str):
        messages = self.message_repo.get_active_thread(session_id)
        return messages

    # =========================
    # GET SESSION MESSAGES FOR DISPLAY 
    # =========================
    async def get_session_messages_for_display(self, session_id: str):
        session = self.session_repo.get(session_id)
        if not session:
            raise ValueError("Session not found")

        messages = self.message_repo.get_active_thread(session_id)

        # Translate messages concurrently instead of one after another.
        # The semaphore caps parallel LLM calls to stay clear of API rate limits.
        semaphore = asyncio.Semaphore(_TRANSLATION_CONCURRENCY)

        async def translate_one(m):
            async with semaphore:
                return await self._translate_message(m, session.language)

        contents = await asyncio.gather(
            *(translate_one(m) for m in messages),
            return_exceptions=True,
        )

        result = []
        for m, content in zip(messages, contents):
            if isinstance(content, Exception):
                # One failed translation must not break the whole chat:
                # show the original text (nothing is cached, so the next
                # open will retry).
                print(f"[translate] message {m.id} failed: {content!r}")
                content = m.content

            result.append(
                MessageResponse(
                    id=m.id,
                    session_id=m.session_id,
                    role=m.role,
                    content=content,
                    image_url=self._build_image_url(m.session_id, m.id) if m.image_path else None,
                    tokens_used=m.tokens_used,
                    created_at=m.created_at,
                )
            )

        return result

    @staticmethod
    def _build_image_url(session_id: str, message_id: int) -> str:
        """
        Points at a Moodle-side relay (ajax/get_image.php), NOT directly at
        this FastAPI service — the browser can only reach Moodle; FastAPI
        (127.0.0.1:8001) is only reachable server-to-server from PHP. The
        relay re-checks require_login()/capability before proxying the
        file through, same as every other endpoint here.
        """
        base = settings.MOODLE_BASE_URL.rstrip("/")
        return f"{base}/local/ai_system/ajax/get_image.php?session_id={session_id}&message_id={message_id}"

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
    async def create_user_message(self, session_id: str, content: str, image_path: str | None = None, parent_id: int | None = None):
        session = self.session_repo.get(session_id)
        if not session:
            raise ValueError("Session not found")

        return self.message_repo.create(
            session_id=session_id,
            role="user",
            content=content,
            image_path=image_path,
            parent_id=parent_id,
        )

    # =========================
    # SAVE ASSISTANT MESSAGE ONLY
    # =========================
    async def create_assistant_message(self, session_id: str, content: str, tokens_used: int | None = None, parent_id: int | None = None):
        session = self.session_repo.get(session_id)
        if not session:
            raise ValueError("Session not found")

        return self.message_repo.create(
            session_id=session_id,
            role="assistant",
            content=content,
            tokens_used=tokens_used,
            parent_id=parent_id,
        )

    def _has_reply(self, session_id: str, parent_id: int) -> bool:
        """True if `parent_id` already has a child message (an answer saved by someone else)."""
        return bool(self.message_repo.get_siblings(session_id, parent_id))

    # =========================
    # SAVE A PARTIAL ASSISTANT ANSWER (user pressed Stop)
    # =========================
    async def create_partial_assistant_message(self, session_id: str, content: str):
        """
        When the user stops a streaming answer, the stream is cut before
        chat_stream() can save the reply. The browser then sends the text it
        has received so far, and it is stored here as the assistant message
        under the last message of the active thread -- which must be the
        user's question that is still waiting for an answer.
        """
        session = self.session_repo.get(session_id)
        if not session:
            raise ValueError("Session not found")

        content = (content or "").strip()
        if not content:
            raise ValueError("Empty partial message")

        thread = await self.get_session_messages(session_id)
        if thread and thread[-1].role == "assistant":
            # Already stored: the backend saves the partial answer itself when
            # the client disconnects, usually before the browser reports it.
            return thread[-1]
        if not thread or thread[-1].role != "user":
            raise ValueError("No unanswered user message to attach the partial answer to")

        message = await self.create_assistant_message(
            session_id, content, parent_id=thread[-1].id
        )
        # If the backend is still generating this answer, tell it to stop.
        _STOP_REQUESTED.add(session_id)
        return message

    def _resolve_search_scope(self, session) -> tuple[str | None, list[int] | None, list[int]]:
        if session.course_id:
            print(f"[scope] course mode: session_id={session.id} course_id={session.course_id}")
            return f"course_{session.course_id}", None, [session.course_id]

        course_ids = list(self.enrolled_courses)
        print(f"[scope] global mode: user_id={session.user_id}, enrolled course_ids={course_ids}")
        return None, (course_ids or None), (course_ids or [])

    # =========================
    # GENERATE FULL RESPONSE
    # =========================
    async def chat(self, session_id: str, content: str, image_base64: str | None = None, image_mime_type: str | None = None):
        session = self.session_repo.get(session_id)
        if not session:
            raise ValueError("Session not found")

        existing_messages = await self.get_session_messages(session_id)
        is_first_message = len(existing_messages) == 0

        collection_name, course_ids, relevant_course_ids = self._resolve_search_scope(session)
        course_link, course_links = self._build_course_link_context(
            session, collection_name, relevant_course_ids
        )

        parent_id = existing_messages[-1].id if existing_messages else None

        image_path = self._save_chat_image(session_id, image_base64, image_mime_type) if image_base64 else None
        user_message = await self.create_user_message(session_id, content, image_path=image_path, parent_id=parent_id)
        history = await self.get_session_messages(session_id)

        history_dicts = [{"role": m.role, "content": m.content} for m in history]
        if image_base64:
            history_dicts[-1] = {
                "role": "user",
                "content": self._build_vision_content(content, image_base64, image_mime_type),
            }

        ai_text = await self.ai_service.generate_response(
            history_dicts,
            collection_name=collection_name,
            course_ids=course_ids,
            course_link=course_link,
            course_links=course_links,
        )
        assistant_message = await self.create_assistant_message(session_id, ai_text, parent_id=user_message.id)

        generated_title = None
        if is_first_message and session.title == "New Chat":
            generated_title = await self.ai_service.generate_title(content, ai_text)
            self.session_repo.update(session_id, title=generated_title)

        user_display = await self._translate_message(user_message, session.language)
        assistant_display = await self._translate_message(assistant_message, session.language)

        return {
            "user": MessageResponse(
                id=user_message.id, session_id=user_message.session_id, role=user_message.role,
                content=user_display, image_url=self._build_image_url(session_id, user_message.id) if image_path else None,
                tokens_used=user_message.tokens_used, created_at=user_message.created_at,
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
    async def chat_stream(self, session_id: str, content: str, image_base64: str | None = None, image_mime_type: str | None = None, result: dict | None = None):
        if result is None:
            result = {}

        session = self.session_repo.get(session_id)
        if not session:
            raise ValueError("Session not found")

        existing_messages = await self.get_session_messages(session_id)
        is_first_message = len(existing_messages) == 0                # NEW
        parent_id = existing_messages[-1].id if existing_messages else None

        collection_name, course_ids, relevant_course_ids = self._resolve_search_scope(session)
        course_link, course_links = self._build_course_link_context(
            session, collection_name, relevant_course_ids
        )

        # The image is written to disk once here; only its relative path is
        # stored in the DB row (see _save_chat_image). The actual base64
        # bytes are handed to the model for this turn only, via the
        # history[-1] override below — they never touch the database.
        image_path = self._save_chat_image(session_id, image_base64, image_mime_type) if image_base64 else None
        user_message = await self.create_user_message(session_id, content, image_path=image_path, parent_id=parent_id)
        result["user_message_id"] = user_message.id

        raw_history = await self.get_session_messages(session_id)
        history = [{"role": msg.role, "content": msg.content} for msg in raw_history]

        if image_base64:
            history[-1] = {
                "role": "user",
                "content": self._build_vision_content(content, image_base64, image_mime_type),
            }

        full_response = ""
        _STOP_REQUESTED.discard(session_id)
        try:
            async for token in self.ai_service.stream_response(
                history,
                collection_name=collection_name,
                course_ids=course_ids,
                course_link=course_link,
                course_links=course_links,
            ):
                full_response += token
                yield token
                if session_id in _STOP_REQUESTED:
                    # "Stop" was pressed: the browser has already stored the partial text.
                    _STOP_REQUESTED.discard(session_id)
                    break
        except (GeneratorExit, asyncio.CancelledError):
            # The client went away (Stop button, closed tab): keep what was
            # generated so far as the answer instead of losing it.
            print(f"[stream] client disconnected after {len(full_response)} chars, session={session_id}")
            # The browser also reports the partial text itself (create_partial_assistant_message);
            # whoever is first saves it, the other one must not add a second answer.
            if full_response.strip() and not self._has_reply(session_id, user_message.id):
                self.message_repo.create(
                    session_id=session_id,
                    role="assistant",
                    content=full_response,
                    parent_id=user_message.id,
                )
            raise

        if self._has_reply(session_id, user_message.id):
            # Stopped by the user: the partial answer is already stored, do not add the full one next to it.
            existing = self.message_repo.get_siblings(session_id, user_message.id)[-1]
            result["assistant_message_id"] = existing.id
        else:
            assistant_message = await self.create_assistant_message(session_id, full_response, parent_id=user_message.id)
            result["assistant_message_id"] = assistant_message.id

        if is_first_message and session.title == "New Chat":           # NEW
            generated_title = await self.ai_service.generate_title(content, full_response)
            self.session_repo.update(session_id, title=generated_title)

    # =========================
    # EDIT A USER MESSAGE (creates a new version + regenerates the reply)
    # =========================
    async def edit_message_stream(self, session_id: str, message_id: int, content: str, result: dict | None = None):
        """
        Creates a new version of a user message (a sibling under the same
        parent) and makes it active, then generates a fresh assistant
        reply as its child -- exactly like a normal turn, except the
        "turn" is inserted in the middle of the tree instead of appended
        at the end. The previous version (and whatever used to follow it)
        is left untouched in the DB with is_active=0, so switching back
        is non-destructive.
        """
        if result is None:
            result = {}

        session = self.session_repo.get(session_id)
        if not session:
            raise ValueError("Session not found")

        original = self.message_repo.get(message_id)
        if not original or original.session_id != session_id or original.role != "user":
            raise ValueError("Message not found")

        new_user_message = self.message_repo.create(
            session_id=session_id,
            role="user",
            content=content,
            image_path=original.image_path,  # editing text only for now
            parent_id=original.parent_id,
            is_active=True,
        )
        # Deactivates `original` (and any older versions) in the same slot.
        self.message_repo.activate(new_user_message.id)
        result["user_message_id"] = new_user_message.id

        collection_name, course_ids, relevant_course_ids = self._resolve_search_scope(session)
        course_link, course_links = self._build_course_link_context(
            session, collection_name, relevant_course_ids
        )

        history = await self.get_session_messages(session_id)  # active thread, now ending at new_user_message
        history_dicts = [{"role": m.role, "content": m.content} for m in history]

        full_response = ""
        _STOP_REQUESTED.discard(session_id)
        try:
            async for token in self.ai_service.stream_response(
                history_dicts,
                collection_name=collection_name,
                course_ids=course_ids,
                course_link=course_link,
                course_links=course_links,
            ):
                full_response += token
                yield token
                if session_id in _STOP_REQUESTED:
                    _STOP_REQUESTED.discard(session_id)
                    break
        except (GeneratorExit, asyncio.CancelledError):
            # Client stopped the stream: keep the partial answer (see chat_stream).
            if full_response.strip() and not self._has_reply(session_id, new_user_message.id):
                self.message_repo.create(
                    session_id=session_id,
                    role="assistant",
                    content=full_response,
                    parent_id=new_user_message.id,
                )
            raise

        if self._has_reply(session_id, new_user_message.id):
            # Stopped by the user: the partial answer is already stored.
            new_assistant_message = self.message_repo.get_siblings(session_id, new_user_message.id)[-1]
        else:
            new_assistant_message = await self.create_assistant_message(
                session_id, full_response, parent_id=new_user_message.id
            )
        result["assistant_message_id"] = new_assistant_message.id
        result.update(self.get_version_info(session_id, new_user_message.id))

    # =========================
    # REGENERATE AN ASSISTANT REPLY (creates a new version)
    # =========================
    async def regenerate_message_stream(self, session_id: str, message_id: int, result: dict | None = None):
        if result is None:
            result = {}

        session = self.session_repo.get(session_id)
        if not session:
            raise ValueError("Session not found")

        original = self.message_repo.get(message_id)
        if not original or original.session_id != session_id or original.role != "assistant":
            raise ValueError("Message not found")

        # History = active thread up to and including the user message
        # that triggered the reply being regenerated.
        full_thread = self.message_repo.get_active_thread(session_id)
        history = []
        for m in full_thread:
            history.append(m)
            if m.id == original.parent_id:
                break

        collection_name, course_ids, relevant_course_ids = self._resolve_search_scope(session)
        course_link, course_links = self._build_course_link_context(
            session, collection_name, relevant_course_ids
        )

        history_dicts = [{"role": m.role, "content": m.content} for m in history]

        full_response = ""
        try:
            async for token in self.ai_service.stream_response(
                history_dicts,
                collection_name=collection_name,
                course_ids=course_ids,
                course_link=course_link,
                course_links=course_links,
            ):
                full_response += token
                yield token
        except (GeneratorExit, asyncio.CancelledError):
            # Client stopped the stream: keep the partial answer as the new version.
            if full_response.strip():
                partial = self.message_repo.create(
                    session_id=session_id,
                    role="assistant",
                    content=full_response,
                    parent_id=original.parent_id,
                    is_active=True,
                )
                self.message_repo.activate(partial.id)
            raise

        new_assistant_message = self.message_repo.create(
            session_id=session_id,
            role="assistant",
            content=full_response,
            parent_id=original.parent_id,
            is_active=True,
        )
        self.message_repo.activate(new_assistant_message.id)
        result["assistant_message_id"] = new_assistant_message.id
        result.update(self.get_version_info(session_id, new_assistant_message.id))

    # =========================
    # VERSION METADATA
    # =========================
    def get_version_info(self, session_id: str, message_id: int) -> dict:
        msg = self.message_repo.get(message_id)
        siblings = self.message_repo.get_siblings(session_id, msg.parent_id)
        ids = [s.id for s in siblings]
        return {
            "version_index": ids.index(message_id) + 1,
            "version_count": len(ids),
            "sibling_ids": ids,
        }

    async def get_session_versions_meta(self, session_id: str) -> dict:
        """
        For every message in the currently active thread that has more
        than one version, returns its position among siblings. Lets the
        frontend render "< i/N >" navigation for the whole history in one
        request instead of one call per message.
        """
        thread = self.message_repo.get_active_thread(session_id)
        meta = {}
        for m in thread:
            siblings = self.message_repo.get_siblings(session_id, m.parent_id)
            if len(siblings) <= 1:
                continue
            ids = [s.id for s in siblings]
            meta[str(m.id)] = {
                "version_index": ids.index(m.id) + 1,
                "version_count": len(ids),
                "sibling_ids": ids,
            }
        return meta

    async def activate_message_version(self, session_id: str, message_id: int):
        message = self.message_repo.get(message_id)
        if not message or message.session_id != session_id:
            raise ValueError("Message not found")
        self.message_repo.activate(message_id)

    def get_image_abs_path(self, session_id: str, message_id: int) -> str | None:
        """
        Resolve a message's stored image_path to an absolute filesystem
        path, scoped to the given session_id (defense in depth — a caller
        can't fetch another session's image just by guessing message_ids;
        the router also independently checks session ownership by user).
        """
        message = self.message_repo.get(message_id)
        if not message or message.session_id != session_id or not message.image_path:
            return None
        return self.image_storage.get_abs_path(session_id, message.image_path)

    def _save_chat_image(self, session_id: str, image_base64: str, image_mime_type: str | None) -> str:
        return self.image_storage.save(session_id, image_base64, image_mime_type)

    @staticmethod
    def _build_vision_content(text: str, image_base64: str, image_mime_type: str | None):
        """Builds the Mistral multimodal content list: text block (if any) + image_url block."""
        mime = image_mime_type or "image/jpeg"
        blocks = []
        if text:
            blocks.append({"type": "text", "text": text})
        blocks.append({
            "type": "image_url",
            "image_url": {"url": f"data:{mime};base64,{image_base64}"},
        })
        return blocks

    def _build_course_link_context(self, session, collection_name, relevant_course_ids):
        if not relevant_course_ids:
            return None, None

        # Names come from the signed request; an id that is not in it falls
        # back to "Course {id}" in format_course_link().
        course_names = {cid: self.enrolled_courses.get(cid) for cid in relevant_course_ids}
        links = build_course_links(course_names)

        if collection_name:
            return links.get(session.course_id), None
        return None, links
