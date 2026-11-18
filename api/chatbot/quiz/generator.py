"""
Generates a quiz from the course materials.

    material (chunks from ChromaDB)  ->  LLM (JSON)  ->  validated Quiz

Where the material comes from:
  - topic given (or scope "chat": the text of the chat as topic) ->
    the normal search (Retriever), so the questions are about that topic;
  - no topic, whole course -> a random sample of chunks spread over all
    files of the course, so a quiz covers the course and not one PDF.

The LLM never writes a source itself: every question names the number of
the material block it is based on, and the backend fills in the citation
link and page from that block's metadata (same links as in chat answers).

Big quizzes are generated in parts of at most 10 questions, in parallel,
each part with its own blocks. Invalid questions (wrong JSON, 3 options,
"correct" out of range, duplicates, ...) are dropped; missing ones are
requested once more.
"""

import asyncio
import json
import random
import re
import time

from pydantic import ValidationError

from chatbot.quiz.schemas import Quiz, QuizQuestion, QuizScope
from rag.retriever import Retriever

try:
    from translation.translator import _LANGUAGE_NAMES
except ImportError:  # pragma: no cover
    _LANGUAGE_NAMES = {"en": "English", "de": "German", "ru": "Russian", "uk": "Ukrainian"}


QUESTIONS_PER_CALL = 5        # one LLM call writes at most this many questions
                              # (parts run in parallel: 10 questions = 2 calls
                              # of 5, much faster than one long answer)
BLOCKS_PER_QUESTION = 2       # material blocks offered per requested question
MAX_BLOCKS_PER_CALL = 16
BLOCK_MAX_CHARS = 1800        # longer chunks are shortened ...
TABLE_MAX_CHARS = 4000        # ... tables a bit less (they are dense)
MIN_BLOCK_CHARS = 200         # too short to ask something sensible about

# "laut Block 2", "(Block 3)", "according to block 1", "в блоке 2", "согласно блоку 4" ...
# The model sometimes cites our internal block numbers; the student has no
# idea what "Block 2" is. Such phrases are cut out; a question that still
# mentions a block afterwards is dropped (and replaced by the retry).
_BLOCK_REF = re.compile(
    r"\s*\(?\s*(?:(?:laut|gemäß|nach|in|im|aus|according to|in|from|согласно|в|во|по|из)\s+)?"
    r"(?:dem\s+|the\s+)?(?:block|блок[а-яё]*)\s*\d+\s*\)?",
    re.IGNORECASE,
)
_BLOCK_LEFT = re.compile(r"\b(?:block|блок[а-яё]*)\s*\d+", re.IGNORECASE)


def _remove_block_refs(text: str) -> str:
    text = _BLOCK_REF.sub(" ", text)
    text = re.sub(r"\s+([?.,!:;])", r"\1", text)   # "Was ermöglicht ... ?" -> "...?"
    text = re.sub(r",,", "", text)                   # "Что, согласно блоку 2, означает" -> "Что означает"
    return re.sub(r"\s{2,}", " ", text).strip()


QUIZ_SYSTEM_PROMPT = """You write quiz questions that help students check their understanding of their course materials.

You get numbered blocks of course material. Write exactly {count} questions in {language}.

RULES
- Every question must be answerable from ONE block alone. Put that block's number in "block". Never use knowledge from outside the blocks.
- The student never sees the blocks: never mention "block", its number or "the text above" in a question, option or explanation. Write questions as if about the subject itself (not "According to block 2, what ..." but "What ...").
- Ask about the subject matter: facts, concepts, relationships, reasons, numbers that matter. Never about file names, page numbers, authors of a document, its layout, or the organisation of the course itself (who coaches it, how many hours it takes, dates).
- Each question has exactly 4 options and exactly one correct option ("correct" = its index, 0-3).
- Wrong options must sound plausible to someone who did not study the material, but be clearly wrong according to the block.
- The right option must NOT be recognisable by its form. All 4 options have the same kind, structure and length; the right one is not the longest or the most detailed one. Do not make wrong options obviously wrong with words like "only", "exclusively", "always", "never", "completely" (or their equivalents in {language}) unless the right option uses such words too.
- No "all of the above" / "none of the above", no trick questions, no negative questions ("Which is NOT ...").
- Spread the questions over different blocks and topics. Never two questions about the same fact.
- "explanation": 1-2 sentences why the correct option is right, based on the block.
- Write question, options and explanation in {language}, also when the block is in another language. Keep names and technical terms as they are in the material.

Answer with JSON only:
{{"questions": [{{"question": "...", "options": ["...", "...", "...", "..."], "correct": 0, "explanation": "...", "block": 1}}]}}"""


class QuizGenerationError(Exception):
    """No quiz could be made (no material found, or the LLM failed)."""


class QuizGenerator:
    def __init__(self, llm, retriever: Retriever, model: str | None = None):
        self.llm = llm
        self.retriever = retriever
        self.model = model or None
        # question text -> text of the block it was made from. Only for the
        # quality test (eval/quiz_eval.py), which gives the block to a judge.
        self.question_blocks: dict[str, str] = {}

    # ─────────────────────────────────────────
    # Public
    # ─────────────────────────────────────────

    async def generate(
        self,
        course_ids: list[int],
        count: int,
        language: str,
        scope: QuizScope = "course",
        topic: str | None = None,
        chat_text: str | None = None,
    ) -> Quiz:
        """
        course_ids: the course of the chat, or all enrolled courses for a
            chat without a course.
        scope: "course" = the whole course (or `topic` in it), "chat" =
            what the current chat was about (`chat_text`).
        language: code of the quiz language ("de", "en", "ru", "uk").
        """
        t0 = time.perf_counter()
        query = (topic or "").strip()
        if scope == "chat":
            query = " ".join(filter(None, [query, (chat_text or "").strip()]))[:2000]
            if not query:
                raise QuizGenerationError("the chat has no text to make a quiz about")

        needed_blocks = min(count * BLOCKS_PER_QUESTION, 60)
        if query:
            chunks = self._search(query, course_ids, needed_blocks)
        else:
            chunks = self._sample(course_ids, needed_blocks)
        if not chunks:
            raise QuizGenerationError("no course material found for this quiz")

        questions = await self._write_questions(chunks, count, language, query)
        if not questions:
            raise QuizGenerationError("the language model returned no usable questions")

        quiz = Quiz(
            scope=scope,
            topic=topic or None,
            language=language,
            questions=questions[:count],
        )
        print(f"[quiz] {len(quiz.questions)}/{count} questions from {len(chunks)} blocks "
              f"({scope}, topic={topic!r}) in {(time.perf_counter() - t0):.1f}s")
        return quiz

    # ─────────────────────────────────────────
    # Material
    # ─────────────────────────────────────────

    def _search(self, query: str, course_ids: list[int], n: int) -> list[dict]:
        """Chunks about the topic, best first (the chat's normal search)."""
        chunks = self.retriever.retrieve_global(query=query, course_ids=course_ids, n_results=n)
        return [c for c in chunks if len(c["text"]) >= MIN_BLOCK_CHARS]

    def _sample(self, course_ids: list[int], n: int) -> list[dict]:
        """
        Random chunks spread over all files of the course(s): round robin
        over the files, a random chunk of each file per round. Without this,
        one 300-page PDF would provide nearly all questions.
        """
        store = self.retriever.vector_store
        by_source: dict[tuple, list[tuple]] = {}
        for course_id in course_ids:
            name = f"course_{course_id}"
            if not store.collection_exists(name):
                continue
            got = store.get_or_create_collection(name).get(include=["documents", "metadatas"])
            for chunk_id, text, meta in zip(got["ids"], got["documents"], got["metadatas"]):
                if not text or len(text) < MIN_BLOCK_CHARS:
                    continue
                meta = {**(meta or {}), "course_id": course_id}
                by_source.setdefault((course_id, meta.get("source", "?")), []).append((chunk_id, text, meta))

        pools = list(by_source.values())
        for pool in pools:
            random.shuffle(pool)
        random.shuffle(pools)

        picked = []
        while pools and len(picked) < n:
            for pool in list(pools):
                if not pool:
                    pools.remove(pool)
                    continue
                chunk_id, text, meta = pool.pop()
                picked.append({"id": chunk_id, "text": text, "metadata": meta})
                if len(picked) >= n:
                    break
        return picked

    # ─────────────────────────────────────────
    # Questions
    # ─────────────────────────────────────────

    async def _write_questions(self, chunks: list[dict], count: int, language: str, topic: str) -> list[QuizQuestion]:
        # Parts of at most QUESTIONS_PER_CALL questions, each with its own blocks.
        sizes = [QUESTIONS_PER_CALL] * (count // QUESTIONS_PER_CALL)
        if count % QUESTIONS_PER_CALL:
            sizes.append(count % QUESTIONS_PER_CALL)
        groups = [chunks[i::len(sizes)] for i in range(len(sizes))]

        results = await asyncio.gather(
            *(self._call(group[:MAX_BLOCKS_PER_CALL], size, language, topic, avoid=[])
              for group, size in zip(groups, sizes)),
            return_exceptions=True,
        )
        questions: list[QuizQuestion] = []
        for result in results:
            if isinstance(result, Exception):
                print(f"[quiz] part failed: {result!r}")
                continue
            self._add_unique(questions, result)

        # One more try for missing questions, with all blocks.
        missing = count - len(questions)
        if missing > 0:
            try:
                extra = await self._call(chunks[:MAX_BLOCKS_PER_CALL], missing, language, topic,
                                         avoid=[q.question for q in questions])
                self._add_unique(questions, extra)
            except Exception as e:
                print(f"[quiz] retry for {missing} missing questions failed: {e!r}")
        return questions

    @staticmethod
    def _add_unique(questions: list[QuizQuestion], new: list[QuizQuestion]) -> None:
        seen = {" ".join(q.question.casefold().split()) for q in questions}
        for q in new:
            key = " ".join(q.question.casefold().split())
            if key not in seen:
                seen.add(key)
                questions.append(q)

    async def _call(self, chunks: list[dict], count: int, language: str, topic: str,
                    avoid: list[str]) -> list[QuizQuestion]:
        """One LLM call: blocks in, validated questions out."""
        language_name = _LANGUAGE_NAMES.get(language, language)
        blocks = []
        for i, chunk in enumerate(chunks, 1):
            meta = chunk["metadata"]
            limit = TABLE_MAX_CHARS if meta.get("content_type") == "table" else BLOCK_MAX_CHARS
            label = meta.get("source", "?") + (f", p. {meta['page']}" if meta.get("page") else "")
            blocks.append(f"[Block {i} — {label}]\n{chunk['text'][:limit]}")

        user = []
        if topic:
            user.append(f"Topic the student wants to practise: {topic[:500]}\n")
        if avoid:
            user.append("Do NOT repeat these questions:\n" + "\n".join(f"- {q}" for q in avoid) + "\n")
        user.append("\n\n".join(blocks))

        messages = [
            {"role": "system", "content": QUIZ_SYSTEM_PROMPT.format(count=count, language=language_name)},
            {"role": "user", "content": "\n".join(user)},
        ]
        kwargs = {"response_format": {"type": "json_object"}}
        if self.model:
            kwargs["model"] = self.model
        raw = await self.llm.chat(messages, **kwargs)
        return self._parse(raw, chunks)

    def _parse(self, raw: str, chunks: list[dict]) -> list[QuizQuestion]:
        """LLM JSON -> valid questions. Broken questions are skipped, not fatal."""
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", (raw or "").strip())
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            start, end = text.find("{"), text.rfind("}")
            try:
                data = json.loads(text[start:end + 1]) if start >= 0 else {}
            except json.JSONDecodeError:
                print(f"[quiz] unparseable LLM output: {text[:200]!r}")
                return []
        items = data.get("questions", []) if isinstance(data, dict) else data
        if not isinstance(items, list):
            return []

        out = []
        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                block = int(item.get("block", 0))
                chunk = chunks[block - 1] if 1 <= block <= len(chunks) else None
                correct = item.get("correct")
                correct = [int(c) for c in correct] if isinstance(correct, list) else [int(correct)]
                question = QuizQuestion(
                    question=_remove_block_refs(str(item.get("question", ""))),
                    options=[_remove_block_refs(str(o)) for o in item.get("options", [])],
                    correct=correct,
                    explanation=_remove_block_refs(str(item.get("explanation", ""))),
                    source=Retriever._format_source_label(chunk["metadata"]) if chunk else "",
                    page=(chunk["metadata"].get("page") or None) if chunk else None,
                )
                if len(question.options) != 4:
                    raise ValueError(f"{len(question.options)} options instead of 4")
                if any(_BLOCK_LEFT.search(t) for t in [question.question, question.explanation, *question.options]):
                    raise ValueError("mentions an internal block number")
            except (ValidationError, ValueError, TypeError) as e:
                print(f"[quiz] question skipped: {str(e).splitlines()[0][:150]}")
                continue
            if chunk:
                self.question_blocks[question.question] = chunk["text"]
            out.append(self._shuffle(question))
        return out

    @staticmethod
    def _shuffle(question: QuizQuestion) -> QuizQuestion:
        """Random option order: LLMs put the right answer first far too often."""
        order = list(range(len(question.options)))
        random.shuffle(order)
        return question.model_copy(update={
            "options": [question.options[i] for i in order],
            "correct": sorted(order.index(c) for c in question.correct),
        })
