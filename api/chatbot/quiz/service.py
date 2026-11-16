"""
Quizzes in a chat: create one, answer its questions, show it.

A quiz is two messages in the chat thread, like a question and its answer:

    user       content_type "quiz_request"  {"scope", "count", "topic"}
    assistant  content_type "quiz"          the Quiz JSON (schemas.py)

So it takes part in everything a chat already does: the thread order,
versions, the sidebar, deleting the chat, privacy export.

The student's answers are in quiz_answers (one per question) and are
checked HERE, on the server. The browser only gets the right option and
the explanation of a question after that question was answered, so the
page source does not give the answers away.
"""

import json
import time

from chatbot.quiz.generator import QuizGenerationError, QuizGenerator
from chatbot.quiz.schemas import QUESTION_COUNTS, Quiz, QuizScope, check_answer
from chatbot.repositories.message_repository import MessageRepository
from chatbot.repositories.quiz_repository import QuizRepository
from chatbot.repositories.session_repository import SessionRepository
from chatbot.services.ai_service import _detect_language_code

CHAT_TEXT_MESSAGES = 6      # scope "chat": the last N text messages are the topic
CHAT_TEXT_CHARS = 2000
SUPPORTED_LANGUAGES = {"de", "en", "ru", "uk"}
DEFAULT_LANGUAGE = "de"     # the course materials are mostly German


class QuizError(Exception):
    """A request that cannot be fulfilled; `code` is shown to the client."""

    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code = code
        self.status = status


# ─────────────────────────────────────────
# Views (what the browser gets) and LLM text
# ─────────────────────────────────────────

def quiz_request_view(message) -> dict:
    try:
        data = json.loads(message.content)
    except (TypeError, json.JSONDecodeError):
        data = {}
    return {
        "scope": data.get("scope", "course"),
        "count": data.get("count"),
        "topic": data.get("topic"),
    }


def quiz_view(message, answers: list | None) -> dict:
    """
    The quiz for the browser. Questions not answered yet come WITHOUT
    the right option, explanation and source.
    """
    quiz = Quiz.from_json(message.content)
    by_index = {a.question_index: a for a in (answers or [])}
    questions = []
    for i, q in enumerate(quiz.questions):
        item = {"type": q.type, "question": q.question, "options": q.options}
        answer = by_index.get(i)
        if answer is not None:
            item.update({
                "answer": json.loads(answer.answer),
                "is_correct": bool(answer.is_correct),
                "correct": q.correct,
                "explanation": q.explanation,
                "source": q.source,
                "page": q.page,
            })
        questions.append(item)
    answered = len(by_index)
    return {
        "scope": quiz.scope,
        "topic": quiz.topic,
        "language": quiz.language,
        "questions": questions,
        "answered": answered,
        "score": sum(1 for a in by_index.values() if a.is_correct),
        "finished": answered >= len(quiz.questions),
    }


def text_for_llm(message) -> str:
    """
    What the chat model sees of a message in the history. Quiz messages
    are JSON; the model gets a short readable note instead, so a follow-up
    question ("explain question 2") still has the context.
    """
    content_type = getattr(message, "content_type", "text") or "text"
    if content_type == "quiz_request":
        r = quiz_request_view(message)
        topic = f" about: {r['topic']}" if r.get("topic") else ""
        return f"(I asked for a quiz with {r.get('count') or '?'} questions{topic}.)"
    if content_type == "quiz":
        try:
            quiz = Quiz.from_json(message.content)
        except Exception:
            return "(A quiz was shown here.)"
        lines = [f"(Quiz with {len(quiz.questions)} questions:)"]
        for i, q in enumerate(quiz.questions, 1):
            right = "; ".join(q.options[c] for c in q.correct)
            lines.append(f"{i}. {q.question} — right answer: {right}")
        return "\n".join(lines)
    return message.content


# ─────────────────────────────────────────
# Service
# ─────────────────────────────────────────

class QuizService:
    def __init__(
        self,
        message_repo: MessageRepository,
        session_repo: SessionRepository,
        quiz_repo: QuizRepository,
        generator: QuizGenerator,
        enrolled_courses: dict[int, str],
    ):
        self.message_repo = message_repo
        self.session_repo = session_repo
        self.quiz_repo = quiz_repo
        self.generator = generator
        self.enrolled_courses = enrolled_courses

    async def create_quiz(
        self,
        session_id: str,
        scope: QuizScope,
        count: int,
        topic: str | None = None,
        language: str | None = None,
    ) -> dict:
        """
        Generates a quiz and appends it to the chat (request + quiz message).
        Returns {"request": message, "quiz": message, "title": new title or None}.
        """
        session = self.session_repo.get(session_id)
        if not session:
            raise QuizError("not_found", "Session not found", 404)
        if count not in QUESTION_COUNTS:
            raise QuizError("bad_count", f"count must be one of {QUESTION_COUNTS}")
        topic = (topic or "").strip()[:300] or None

        thread = self.message_repo.get_active_thread(session_id)
        chat_text = self._chat_text(thread) if scope == "chat" else None
        if scope == "chat" and not chat_text:
            raise QuizError("empty_chat", "This chat has no messages to make a quiz about yet")

        course_ids = [session.course_id] if session.course_id else list(self.enrolled_courses)
        if not course_ids:
            raise QuizError("no_course", "No course to make a quiz from")

        language = self._language(language, session, thread)
        try:
            quiz = await self.generator.generate(
                course_ids=course_ids, count=count, language=language,
                scope=scope, topic=topic, chat_text=chat_text,
            )
        except QuizGenerationError as e:
            raise QuizError("no_material", str(e), 422)

        parent_id = thread[-1].id if thread else None
        request_message = self.message_repo.create(
            session_id=session_id,
            role="user",
            content=json.dumps({"scope": scope, "count": count, "topic": topic}, ensure_ascii=False),
            content_type="quiz_request",
            parent_id=parent_id,
        )
        quiz_message = self.message_repo.create(
            session_id=session_id,
            role="assistant",
            content=quiz.to_json(),
            content_type="quiz",
            parent_id=request_message.id,
        )

        # A new chat that starts with a quiz gets a title right away
        # (no LLM call needed: topic or course name).
        title = None
        if not thread and (session.title in (None, "", "New Chat")):
            name = topic or self.enrolled_courses.get(session.course_id or 0) or ""
            title = f"Quiz: {name}"[:255] if name else "Quiz"
            self.session_repo.update(session_id, title=title)
        else:
            self.session_repo.update(session_id)  # last activity (sidebar order)

        return {"request": request_message, "quiz": quiz_message, "title": title}

    def answer(self, session_id: str, message_id: int, question_index: int, answer: list[int]) -> dict:
        """
        Checks and stores the answer to one question. A question is answered
        once: answering again returns the first answer unchanged.
        Returns the updated quiz view and the result of this question.
        """
        message = self.message_repo.get(message_id)
        if not message or message.session_id != session_id or message.content_type != "quiz":
            raise QuizError("not_found", "Quiz not found", 404)
        quiz = Quiz.from_json(message.content)
        if not 0 <= question_index < len(quiz.questions):
            raise QuizError("bad_question", "No such question")
        question = quiz.questions[question_index]
        answer = sorted({int(a) for a in answer})
        if not answer or any(a < 0 or a >= len(question.options) for a in answer):
            raise QuizError("bad_answer", "Choose one of the options")
        if question.type == "single_choice" and len(answer) != 1:
            raise QuizError("bad_answer", "Choose exactly one option")

        self.quiz_repo.save_answer(message_id, question_index, answer, check_answer(question, answer))
        answers = self.quiz_repo.get_answers([message_id]).get(message_id, [])
        view = quiz_view(message, answers)
        return {"question_index": question_index, "result": view["questions"][question_index], "quiz": view}

    # ─────────────────────────────────────────

    @staticmethod
    def _chat_text(thread) -> str:
        """The recent text messages of the chat (quizzes left out)."""
        texts = [m.content for m in thread if (m.content_type or "text") == "text" and m.content]
        return "\n".join(texts[-CHAT_TEXT_MESSAGES:])[-CHAT_TEXT_CHARS:]

    @staticmethod
    def _language(requested: str | None, session, thread) -> str:
        """The language the student uses: chosen in the UI > chat language
        setting > language of the student's own messages > German."""
        for code in (requested, session.language):
            if code and code.lower() in SUPPORTED_LANGUAGES:
                return code.lower()
        for m in reversed(thread):
            if m.role == "user" and (m.content_type or "text") == "text":
                code = _detect_language_code(m.content)
                if code in SUPPORTED_LANGUAGES:
                    return code
        return DEFAULT_LANGUAGE
