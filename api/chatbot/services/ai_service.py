import re
import time

from langdetect import detect, DetectorFactory
from langdetect.lang_detect_exception import LangDetectException

from chatbot.prompts import RAG_SYSTEM_PROMPT, RAG_CONTEXT_TEMPLATE, NO_CONTEXT_PROMPT
from llm.base import BaseLLM
from settings import settings
from rag.retriever import Retriever
from translation.translator import Translator

# Makes langdetect's output deterministic across runs (it's internally
# probabilistic otherwise, which would make the same question sometimes
# detected as one language, sometimes another).
DetectorFactory.seed = 0

# Languages the embedding model aligns well with the (mostly German)
# course materials on its own — no retrieval-query translation needed.
_RETRIEVAL_SAFE_LANGUAGES = {"en", "de"}


# Below this many characters langdetect is a coin toss -- and it is
# confidently wrong: "sag mehr" -> "tl" (Tagalog, 0.99999), "explain more"
# -> "fr". Its probability value says nothing about this, so reliability is
# decided by length (see _detect_language_code).
_MIN_CHARS_FOR_RELIABLE_DETECTION = 20


def _has_non_latin_letters(text: str) -> bool:
    """Cyrillic, Greek, Arabic, CJK ... -- the script alone gives the language away, even in a few characters."""
    return any(ch.isalpha() and ord(ch) > 0x024F for ch in text)


# Quoted titles/terms are usually in the language of the SOURCE, not of the
# student: „Learning to Serve: Promoting Civil Society …“ made a German
# question detect as "en".
_QUOTED = re.compile(r"„[^“”\"]*[“”\"]|“[^”]*”|«[^»]*»|\"[^\"]*\"")

_UKRAINIAN_ONLY = set("іїєґІЇЄҐ")
_RUSSIAN_ONLY = set("ыэёъЫЭЁЪ")


_IMAGE_KEYWORDS_PROMPT = (
    "Name the subject of this image as a search query: the topic and the "
    "6-12 most specific terms, names and numbers visible in it (e.g. a slide "
    "title, technical terms). Use the language of the text in the image. "
    "Reply with the keywords only, on one line, no sentences."
)


def _detect_cyrillic(words: list[str]) -> str:
    """
    Language of Cyrillic text. langdetect alone confuses short Russian with
    Bulgarian ("Что означает аббревиатура VUCA?" -> "bg"), so letters that
    exist in only one alphabet decide first.
    """
    joined = " ".join(words)
    if any(ch in _UKRAINIAN_ONLY for ch in joined):
        return "uk"
    if any(ch in _RUSSIAN_ONLY for ch in joined):
        return "ru"
    try:
        code = detect(joined)
    except LangDetectException:
        return "ru"
    # bg/mk on text without their own letters is almost always Russian here.
    return "ru" if code in {"bg", "mk"} else code


def _detect_language_code(text: str) -> str | None:
    """
    ISO 639-1 code (e.g. "en", "de", "ru") of the given text, or None if
    the detection would not be reliable: short Latin-script text such as
    "sag mehr" or "warum?" (langdetect returns random languages for it,
    with very high "confidence"). Callers then fall back to the language
    of earlier messages (_detect_conversation_language).

    Two things the student did NOT write in their own language are ignored:
    - quoted titles/terms („…“, "…", «…»);
    - in a non-Latin-script question, the Latin-script words (English terms
      such as "Europe Engage", "service-learning"): "Как Europe Engage
      определяет service-learning?" used to come out as "et" (Estonian)
      and the bot answered in Estonian.

    No name lookup here on purpose — passing the raw code to the LLM (see
    _language_directive_block) works for any of the ~55 languages
    langdetect supports, not just ones we've bothered to name.
    """
    text = (text or "").strip()
    without_quotes = _QUOTED.sub(" ", text).strip()
    if len(without_quotes) >= 3:
        text = without_quotes
    if len(text) < 3:
        return None

    if _has_non_latin_letters(text):
        native = [w for w in re.findall(r"\w+", text) if _has_non_latin_letters(w)]
        if native and any("\u0400" <= ch <= "\u04FF" for w in native for ch in w):
            return _detect_cyrillic(native)
        text = " ".join(native) or text
    elif len(text) < _MIN_CHARS_FOR_RELIABLE_DETECTION:
        return None
    try:
        return detect(text)
    except LangDetectException:
        return None


_TITLE_SYSTEM_PROMPT = (
    "Generate a short, descriptive title (3-6 words) summarizing this chat exchange. "
    "Write the title in the same language as the conversation. "
    "Return ONLY the title text — no quotes, no trailing punctuation, no explanations."
)


class AIService:
    def __init__(
        self,
        llm: BaseLLM,
        retriever: Retriever = None,
        translator: Translator = None,
        retrieval_n_results: int = 12,
    ):
        """
        translator: needed for _translate_for_retrieval (non-EN/DE questions
            are translated to English before the vector search). Without it
            that step is silently skipped.
        retrieval_n_results: how many chunks are sent to the LLM as context.
            A parameter (not hard-coded) so eval/run_eval.py can compare values.
        """
        self.llm = llm
        self.retriever = retriever
        self.translator = translator
        self.retrieval_n_results = retrieval_n_results

    async def generate_title(self, user_message: str, assistant_message: str) -> str:
        t0 = time.perf_counter()
        messages = [
            {"role": "system", "content": _TITLE_SYSTEM_PROMPT},
            {"role": "user", "content": f"Student: {user_message}\nAssistant: {assistant_message}"},
        ]
        # Own model possible (TITLE_MODEL): on rate-limited keys the title
        # then does not use up the answer model's requests.
        title_model = getattr(settings, "TITLE_MODEL", "") or None
        title = await self.llm.chat(messages, **({"model": title_model} if title_model else {}))
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
        retrieval_query, last_user_message = await self._search_texts(messages)

        formatted = self._format(messages)
        system_prompt = await self._build_system_prompt_with_fallback(
            retrieval_query, last_user_message,
            collection_name=collection_name, course_ids=course_ids,
            course_link=course_link, course_links=course_links,
        )
        language_code = self._detect_conversation_language(messages)
        system_prompt += self._language_directive_block(language_code)
        self._inject_inline_language_directive(formatted, language_code)

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

        retrieval_query, last_user_message = await self._search_texts(messages)

        formatted = self._format(messages)
        system_prompt = await self._build_system_prompt_with_fallback(
            retrieval_query, last_user_message,
            collection_name=collection_name, course_ids=course_ids,
            course_link=course_link, course_links=course_links,
        )
        language_code = self._detect_conversation_language(messages)
        system_prompt += self._language_directive_block(language_code)
        self._inject_inline_language_directive(formatted, language_code)
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

    async def _search_texts(self, messages) -> tuple[str, str]:
        """
        (retrieval_query, last_user_message) for the course-material search.

        With an image in the latest message the TEXT is usually generic
        ("what is this slide about?") and says nothing about the topic, so
        the search returned some loosely related chunk and the answer cited
        a course file that had nothing to do with the image. Then the image
        is first described in a few keywords by the vision model, and those
        keywords are searched for: an image on another topic finds nothing
        in the course (-> answer without citation), an image of course
        material finds the right chunks.
        """
        retrieval_query = self._build_retrieval_query(messages)
        last_user_message = self._get_last_user_message(messages)

        image_block = self._last_user_image_block(messages)
        if image_block is None:
            return retrieval_query, last_user_message

        try:
            t0 = time.perf_counter()
            kw_model = getattr(settings, "IMAGE_KEYWORDS_MODEL", "") or None
            keywords = (await self.llm.chat([{
                "role": "user",
                "content": [
                    {"type": "text", "text": _IMAGE_KEYWORDS_PROMPT},
                    image_block,
                ],
            }], **({"model": kw_model} if kw_model else {}), max_tokens=80)).strip()
            print(f"[image-search] keywords: {keywords[:200]!r} ({(time.perf_counter() - t0) * 1000:.0f} ms)")
        except Exception as e:
            # Search with the text alone rather than failing the answer.
            print(f"[image-search] keyword extraction failed: {e!r}")
            return retrieval_query, last_user_message

        last_with_image = f"{last_user_message} {keywords}".strip()
        return f"{retrieval_query} {keywords}".strip(), last_with_image

    @staticmethod
    def _last_user_image_block(messages):
        for msg in reversed(messages):
            role = msg["role"] if isinstance(msg, dict) else msg.role
            if role != "user":
                continue
            content = msg["content"] if isinstance(msg, dict) else msg.content
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "image_url":
                        return block
            return None
        return None

    async def _translate_search_texts(self, retrieval_query: str, last_user_message: str) -> tuple[str, str]:
        """
        Both search texts, translated if needed. On the first question of a
        chat they are the same text, so it is translated only once (saves a
        whole LLM round trip for e.g. Russian questions).
        """
        retrieval_query_for_search = await self._translate_for_retrieval(retrieval_query)
        if last_user_message == retrieval_query:
            return retrieval_query_for_search, retrieval_query_for_search
        last_message_for_search = await self._translate_for_retrieval(last_user_message)
        return retrieval_query_for_search, last_message_for_search

    def _needs_translation(self, *texts: str) -> bool:
        if not self.translator:
            return False
        for text in texts:
            code = _detect_language_code(text or "")
            if code is not None and code not in _RETRIEVAL_SAFE_LANGUAGES:
                return True
        return False

    async def _build_system_prompt_with_fallback(
        self, retrieval_query: str, last_user_message: str, **scope
    ) -> str:
        """
        Search with the student's ORIGINAL text first — the embedding model
        is multilingual and matches Russian/Ukrainian questions to the
        German/English materials on its own (eval: 16/16 RU/UK questions
        found the answer chunk with AND without translation). Only when that
        finds nothing at all, translate the search text to English and
        search again. Saves a Mistral round trip (~1-3 s) on every non-EN/DE
        question, keeps the old rescue for the rare case it is needed.
        """
        prompt = await self._build_system_prompt(
            retrieval_query, last_message=last_user_message, **scope
        )
        has_scope = bool(scope.get("collection_name") or scope.get("course_ids"))
        if (
            prompt is not NO_CONTEXT_PROMPT
            or not has_scope  # not enrolled anywhere: nothing to search, nothing to translate for
            or not self._needs_translation(last_user_message, retrieval_query)
        ):
            return prompt

        query_en, last_en = await self._translate_search_texts(retrieval_query, last_user_message)
        if (query_en, last_en) == (retrieval_query, last_user_message):
            return prompt
        print("[retrieval-translate] nothing found with the original text, retrying in English")
        return await self._build_system_prompt(query_en, last_message=last_en, **scope)

    async def _translate_for_retrieval(self, text: str) -> str:
        """
        The embedding model aligns English and German with each other
        reasonably well, but other languages (observed: Russian) show much
        weaker cross-lingual similarity to the mostly-German course
        materials — relevant chunks end up scoring below min_score even
        though they genuinely answer the question.

        Fix: translate the SEARCH text (never the text shown to the
        student — that's handled separately by the language-directive
        methods below) into English before embedding it, whenever the
        detected language isn't already English or German. Falls back to
        the original text if detection or translation fails, so a
        translation hiccup degrades retrieval quality rather than
        breaking the request.
        """
        if not text or not text.strip() or not self.translator:
            return text

        code = _detect_language_code(text)
        if code is None or code in _RETRIEVAL_SAFE_LANGUAGES:
            return text

        try:
            translated = await self.translator.translate(text, "en")
            return translated or text
        except Exception as e:
            print(f"[retrieval-translate] failed for lang={code!r}, using original query: {e!r}")
            return text

    def _detect_conversation_language(self, messages) -> str | None:
        """
        Language of the conversation: that of the newest user message in
        which it can be detected reliably. A short follow-up ("sag mehr",
        "warum?", "and the second one?") cannot be detected on its own,
        so it inherits the language of the previous question instead of
        being given a random one. None if no message is long enough, in
        which case no directive is added and the system prompt's own
        language rule applies.
        """
        for msg in reversed(messages):
            role = msg["role"] if isinstance(msg, dict) else msg.role
            if role != "user":
                continue
            content = msg["content"] if isinstance(msg, dict) else msg.content
            code = _detect_language_code(self._extract_text(content))
            if code:
                return code
        return None

    @staticmethod
    def _language_directive_block(code: str | None) -> str:
        """
        Appended to the END of the system prompt, i.e. right after the
        (possibly huge, mostly-German) retrieved context — this is a
        fallback/reinforcement for _inject_inline_language_directive below,
        which is the stronger of the two because it sits right next to the
        actual question.

        Passes the raw ISO 639-1 code (e.g. "ru", "tr") rather than a
        looked-up display name — the model reliably knows what these codes
        mean, so no hardcoded code->name table is needed, and this works
        for any language langdetect can detect, not just ones we bothered
        to list.
        """
        if not code:
            return ""
        return (
            "\n\n===========================================================\n"
            f"LANGUAGE CHECK: the student's conversation has been automatically "
            f"detected as ISO 639-1 language code \"{code}\". Write your "
            f"entire answer in that language — every sentence, including any "
            f"\"not covered\" statement and the final Source line — no matter "
            f"what language the course materials above are written in.\n"
            "==========================================================="
        )

    @staticmethod
    def _inject_inline_language_directive(formatted: list[dict], code: str | None) -> None:
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

        if not code:
            return

        directive = (
            f"\n\n[System note: the ISO 639-1 language code of this question is "
            f"\"{code}\" — answer in that language, regardless of the language "
            f"of any course materials you were given.]"
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

        `query`/`last_message` here are already the RETRIEVAL-side texts
        (possibly translated by _translate_for_retrieval above) — they are
        used only for the vector search, never shown to the student or
        passed to the final answer-generation call.

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
                n_results=self.retrieval_n_results,
                course_link=course_link,
            )
        elif course_ids:
            context = self.retriever.retrieve_as_context_global_smart(
                last_message=last_message or query,
                combined_query=query,
                course_ids=course_ids,
                n_results=self.retrieval_n_results,
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
    