import time

from langdetect import detect, DetectorFactory
from langdetect.lang_detect_exception import LangDetectException

from chatbot.prompts import RAG_SYSTEM_PROMPT, RAG_CONTEXT_TEMPLATE, NO_CONTEXT_PROMPT
from llm.base import BaseLLM
from rag.retriever import Retriever

# Makes langdetect's output deterministic across runs (it's internally
# probabilistic otherwise, which would make the same question sometimes
# detected as one language, sometimes another).
DetectorFactory.seed = 0

_LANGUAGE_NAMES = {
    "en": "English",
    "de": "German",
    "ru": "Russian",
    "uk": "Ukrainian",
    "fr": "French",
    "es": "Spanish",
    "it": "Italian",
    "pl": "Polish",
    "tr": "Turkish",
    "ar": "Arabic",
}


def _detect_language_name(text: str) -> str | None:
    """
    Best-effort language name for the explicit "answer in X" directive.
    Returns None when detection isn't possible/reliable (very short text,
    e.g. a single word or "hi") -- callers fall back to the generic
    language-matching instruction already in the prompt in that case.
    """
    text = (text or "").strip()
    if len(text) < 3:
        return None
    try:
        code = detect(text)
    except LangDetectException:
        return None
    return _LANGUAGE_NAMES.get(code, code)


_TITLE_SYSTEM_PROMPT = (
    "Generate a short, descriptive title (3-6 words) summarizing this chat exchange. "
    "Write the title in the same language as the conversation. "
    "Return ONLY the title text — no quotes, no trailing punctuation, no explanations."
)


class AIService:
    def __init__(self, llm: BaseLLM, retriever: Retriever = None):
        self.llm = llm
        self.retriever = retriever
        
    async def generate_title(self, user_message: str, assistant_message: str) -> str:
        t0 = time.perf_counter()
        messages = [
            {"role": "system", "content": _TITLE_SYSTEM_PROMPT},
            {"role": "user", "content": f"Student: {user_message}\nAssistant: {assistant_message}"},
        ]
        title = await self.llm.chat(messages)
        print(f"[timing] title generation: {(time.perf_counter() - t0) * 1000:.0f} ms")
        return title.strip().strip('"').strip("'")[:255]

    async def generate_response(
        self,
        messages,
        collection_name: str = None,
        course_ids: list[int] = None,
        course_link: str = None,
        course_links: dict[int, str] = None,
    ):
        retrieval_query = self._build_retrieval_query(messages)
        last_user_message = self._get_last_user_message(messages)
        formatted = self._format(messages)
        system_prompt = await self._build_system_prompt(
            retrieval_query, collection_name, course_ids, course_link, course_links, last_message=last_user_message,
        )
        system_prompt += self._language_directive_block(last_user_message)
        self._inject_inline_language_directive(formatted, last_user_message)

        formatted.insert(0, {
            "role": "system",
            "content": system_prompt,
        })

        return await self.llm.chat(formatted)

    async def stream_response(
        self,
        messages,
        collection_name: str = None,
        course_ids: list[int] = None,
        course_link: str = None,
        course_links: dict[int, str] = None,
    ):
        t_start = time.perf_counter()

        retrieval_query = self._build_retrieval_query(messages)
        last_user_message = self._get_last_user_message(messages)
        formatted = self._format(messages)
        system_prompt = await self._build_system_prompt(
            retrieval_query, collection_name, course_ids, course_link, course_links, last_message=last_user_message,
        )
        system_prompt += self._language_directive_block(last_user_message)
        self._inject_inline_language_directive(formatted, last_user_message)
        t_retrieval = time.perf_counter()

        formatted.insert(0, {
            "role": "system",
            "content": system_prompt,
        })

        first_token = True
        async for token in self.llm.stream(formatted):
            if first_token:
                first_token = False
                t_first = time.perf_counter()
                print(
                    f"[timing] retrieval + prompt: {(t_retrieval - t_start) * 1000:.0f} ms | "
                    f"LLM time to first token: {(t_first - t_retrieval) * 1000:.0f} ms | "
                    f"system prompt: {len(system_prompt)} chars"
                )
            yield token

        print(f"[timing] LLM generation total: {(time.perf_counter() - t_retrieval) * 1000:.0f} ms")

    @staticmethod
    def _language_directive_block(last_user_message: str) -> str:
        """
        Appended to the END of the system prompt, i.e. right after the
        (possibly huge, mostly-German) retrieved context — this is a
        fallback/reinforcement for _inject_inline_language_directive below,
        which is the stronger of the two because it sits right next to the
        actual question.
        """
        language_name = _detect_language_name(last_user_message)
        if not language_name:
            return ""
        return (
            "\n\n===========================================================\n"
            f"LANGUAGE CHECK: the student's question has been automatically "
            f"detected as {language_name}. Write your entire answer in "
            f"{language_name} — every sentence, including any \"not covered\" "
            f"statement and the final Source line — no matter what language "
            f"the course materials above are written in.\n"
            "==========================================================="
        )

    @staticmethod
    def _inject_inline_language_directive(formatted: list[dict], last_user_message: str) -> None:
        """
        Appends the same directive directly onto the last user turn (the
        message immediately preceding generation), NOT into the stored
        conversation -- `formatted` is a fresh list built by _format(),
        so this never touches what's persisted in the database. Models
        generally follow instructions placed close to the end of the
        prompt more reliably than ones buried earlier in a long system
        message, so this is the primary mechanism; the system-prompt
        block above is a secondary reinforcement.
        """
        if not formatted or formatted[-1]["role"] != "user":
            return

        language_name = _detect_language_name(last_user_message)
        if not language_name:
            return

        directive = (
            f"\n\n[System note: answer the above in {language_name}, regardless "
            f"of the language of any course materials you were given.]"
        )

        content = formatted[-1]["content"]
        if isinstance(content, str):
            formatted[-1]["content"] = content + directive
        elif isinstance(content, list):
            # Vision turn (image attached): content is a list of blocks,
            # append the directive as one more text block.
            formatted[-1]["content"] = content + [{"type": "text", "text": directive}]

    async def _build_system_prompt(
        self,
        query: str,
        collection_name: str = None,
        course_ids: list[int] = None,
        course_link: str = None,
        course_links: dict[int, str] = None,
        last_message: str = None,
    ) -> str:
        """
        Priority:
        1. If a specific course is selected (collection_name) — search only that course.
        2. Otherwise, if the user has enrolled courses (course_ids) — search across all of them.
        3. Otherwise — plain LLM, no RAG context.

        `query` is the combined (last-N-messages) retrieval query, `last_message`
        is just the latest user message -- the "smart" retrieval methods try
        last_message alone first (see retriever.py) so a sudden topic switch
        within a chat doesn't get diluted by an unrelated earlier question.

        course_link / course_links: pre-built markdown link(s) for the
        course(s) in scope (see chatbot/course_links.py). These are
        purely cosmetic for citation — retrieval itself is unaffected
        whether they're passed or not.
        """
        if not self.retriever or not query:
            return NO_CONTEXT_PROMPT

        if collection_name:
            context = self.retriever.retrieve_as_context_smart(
                last_message=last_message or query,
                combined_query=query,
                collection_name=collection_name,
                n_results=8,
                course_link=course_link,
            )
        elif course_ids:
            context = self.retriever.retrieve_as_context_global_smart(
                last_message=last_message or query,
                combined_query=query,
                course_ids=course_ids,
                n_results=8,
                course_links=course_links,
            )
        else:
            context = ""

        if not context:
            return NO_CONTEXT_PROMPT

        return RAG_SYSTEM_PROMPT + RAG_CONTEXT_TEMPLATE.format(context=context)

    def _get_last_user_message(self, messages) -> str:
        """Extract the last user message text."""
        for msg in reversed(messages):
            role = msg["role"] if isinstance(msg, dict) else msg.role
            content = msg["content"] if isinstance(msg, dict) else msg.content
            if role == "user":
                return self._extract_text(content)
        return ""

    def _build_retrieval_query(self, messages, max_user_messages: int = 2) -> str:
        """
        Builds the text used for vector search.

        Using ONLY the very last user message breaks on short follow-up
        questions like "which file is this from?" or "can you explain
        that more?" — on their own, such messages carry almost no topical
        signal, so the embedding search drifts to unrelated chunks even
        though the conversation is clearly still about the previous topic.

        Fix: concatenate the last `max_user_messages` user messages (most
        recent last, since some embedding models weight later tokens
        more). This keeps retrieval anchored to the actual topic being
        discussed without needing a separate LLM call to rewrite the
        query.

        NOTE: this is a heuristic, not a full query-rewrite step. For
        longer/more tangled conversations, consider replacing this with
        an explicit "condense the question given chat history" LLM call
        instead — more robust, but adds latency and an extra LLM call
        per turn.
        """
        user_messages = []
        for msg in messages:
            role = msg["role"] if isinstance(msg, dict) else msg.role
            content = msg["content"] if isinstance(msg, dict) else msg.content
            if role == "user" and content:
                text = self._extract_text(content)
                if text:
                    user_messages.append(text)

        recent = user_messages[-max_user_messages:]
        return "\n".join(recent)

    @staticmethod
    def _extract_text(content) -> str:
        """
        `content` is either a plain string (text-only turn) or a list of
        Mistral-style content blocks when an image was attached, e.g.:
            [{"type": "text", "text": "..."}, {"type": "image_url", ...}]
        Only the text block(s) are useful for building a search query —
        image blocks contribute nothing to the embedding text.
        """
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return " ".join(
                block.get("text", "")
                for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            ).strip()
        return ""

    def _format(self, messages):
        formatted = []
        for m in messages:
            formatted.append({
                "role": m["role"] if isinstance(m, dict) else m.role,
                "content": m["content"] if isinstance(m, dict) else m.content,
            })

        while formatted and formatted[-1]["role"] == "assistant":
            formatted.pop()

        return formatted
    