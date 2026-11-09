"""
Automatic quality test for the SDG Campus chatbot.

Runs every question of eval/questions.json through the REAL backend code
(AIService + Retriever + ChromaDB + Mistral, exactly the objects FastAPI
uses — no HTTP, no Moodle, no chat DB) and scores three things:

  1. Retrieval  — was the chunk with the answer ("evidence") among the
                  chunks sent to the LLM? If not: WHY (not in the index at
                  all / score below min_score / pushed out of the top-N).
                  Also reported: was at least the right PDF there.
  2. Answer     — graded by an LLM judge against the expected answer:
                  correct / partial / wrong.
  3. Extras     — answer in the question's language? expected source cited?

Results go to eval/results/<timestamp>/ (results.json + results.csv for
Excel), and the console summary is compared with the previous run, so
every change shows what it fixed and what it broke.

Run from the api/ folder (venv active, .env present, Chroma data in place):

    python -m eval.run_eval                        # full run, ~40 questions
    python -m eval.run_eval --retrieval-only       # only the search step: fast, nearly free
    python -m eval.run_eval --only 5,13,27         # a few questions
    python -m eval.run_eval --group Cross-language
    python -m eval.run_eval --n-results 8 --label n8        # compare settings
    python -m eval.run_eval --no-retrieval-translation --label no-tr
    python -m eval.run_eval --as-chats             # questions in their chat order, with history
    python -m eval.run_eval --judge-only           # check the JUDGE against your manual Yes/No

Questions are independent single-turn chats by default (reproducible).
--as-chats replays them in the chat order of the sheet, each answer kept
in the history — closer to the manual test, tests follow-up retrieval.
"""

import argparse
import asyncio
import csv
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from eval.build_dataset import normalize

EVAL_DIR = Path(__file__).parent
DATASET_PATH = EVAL_DIR / "questions.json"
RESULTS_DIR = EVAL_DIR / "results"

VERDICT_POINTS = {"correct": 1.0, "partial": 0.5, "wrong": 0.0}

FACTS_JUDGE_PROMPT = """You check whether a chatbot answer contains given key facts.

You get the student's question, the chatbot's ANSWER and a numbered list
of KEY FACTS. For EACH key fact decide whether the answer states it.

- The answer may use other words or another language, other number
  formats or units ("45 bis 90 Minuten" = "45-90 minutes", "1.061" =
  "1,061", "Hannover" = "Hanover"). Same meaning counts as present.
- A fact is present only if the answer states it as true. Saying the
  materials do not contain it, or stating a different value, is "absent".
- For every present fact, copy the exact words from the answer that state
  it into "quote" (verbatim, short). For absent facts, quote "".
- Check facts independently. Do not judge anything else (style, extra
  details, language, source line).
- Separately, set "claims_not_covered" to true if the answer anywhere SAYS
  that the course materials do not contain / do not cover / do not mention
  the answer to the question (in any language, e.g. "I don't see this
  covered", "nicht in den Materialien", "в материалах нет"). Saying that
  only about a side detail that is not asked for does not count.

Reply with JSON only:
{"facts": [{"n": 1, "present": true, "quote": "..."}, ...], "claims_not_covered": false}"""


JUDGE_SYSTEM_PROMPT = """You grade the answers of a university course chatbot.
The chatbot answers students' questions from course PDFs (RAG).

You get: the question group, the student's question, the EXPECTED answer
(written by the teacher) and the chatbot's ACTUAL answer.

Grading rules:
- Key facts are ONLY the facts that directly answer what the question
  asks. Background in the expected answer — text in parentheses, "also",
  "e.g.", legal basis, context — is optional and must not lower the grade.
- Read the whole actual answer carefully before saying a fact is missing;
  the same fact may be worded differently or in another language
  ("45 bis 90 Minuten" = "45–90 minutes").
- If the expected answer states facts: "correct" = all key facts are there
  (numbers, names, years must match; extra correct detail is fine).
  "partial" = some key facts are missing, or the correct facts come with
  a clearly wrong extra claim. "wrong" = most key facts are missing or
  contradicted, or the chatbot says the materials do not cover it.
- If the expected answer describes a required BEHAVIOUR (refuse, say it is
  not in the materials, correct a false premise, not use course content,
  not invent data): grade only whether that behaviour is met. Inventing
  data that is said to be absent is "wrong".
- Ignore the answer's language, formatting and its "Source:" line — those
  are checked separately.

Reply with JSON only:
{"verdict": "correct" | "partial" | "wrong", "reason": "<one short sentence in English>"}"""


# ─────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────

def load_dataset() -> tuple[list[dict], dict[int, str]]:
    data = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    names = {int(k): v for k, v in data["course_names"].items()}
    return data["questions"], names


def matches(source: str | None, key: str | None) -> bool:
    return bool(source and key and key in normalize(source))


def has_evidence(text: str | None, patterns: list[str]) -> bool:
    """True if the chunk text matches ALL evidence regexes (see build_dataset.EVIDENCE)."""
    if not text or not patterns:
        return False
    flat = re.sub(r"\s+", " ", text)
    return all(re.search(p, flat, re.I) for p in patterns)


async def with_retry(factory, what: str, tries: int = 4):
    """Mistral returns 429 under load; wait and retry instead of losing the question."""
    for attempt in range(tries):
        try:
            return await factory()
        except Exception as e:
            status = getattr(e, "status_code", None)
            # 4xx other than 429 (bad key, model not in subscription, bad
            # request) will fail the same way again — stop immediately.
            if attempt == tries - 1 or (status and 400 <= status < 500 and status != 429):
                raise
            wait = 3 * 2 ** attempt
            print(f"  [retry] {what}: {e!r} — again in {wait}s")
            await asyncio.sleep(wait)


# Second, deterministic signal for "says the materials don't cover it"
# (the judge alone may miss it). Only the FIRST 300 characters are checked:
# the problem case is an answer that OPENS with a refusal.
_NOT_COVERED = re.compile(
    r"\bi don'?t see\b|not (covered|mentioned|included) in|do(es)? not (cover|mention|contain|specify)"
    r"|nicht in den (bereitgestellten |vorliegenden )?(kurs)?materialien|enthalten keine|keine (angaben|informationen)"
    r"|в (предоставленных |учебных )?материалах (нет|не )|не (содержат|упомина)|у матеріалах (немає|не )",
    re.I,
)


_NUM = re.compile(r"\d+(?:[.,]\d+)*")


def _numbers(text: str) -> set[str]:
    """Numbers with 2+ digits, thousands separators removed ("1.061" -> "1061", "134,8" stays)."""
    out = set()
    for n in _NUM.findall(text or ""):
        n = re.sub(r"(?<=\d)[.,](?=\d{3}\b)", "", n)
        if sum(ch.isdigit() for ch in n) >= 2:
            out.add(n.replace(",", "."))
    return out


def ungrounded_numbers(answer: str, question: str, chunks: list[dict]) -> list[str]:
    """
    Numbers in the answer that appear neither in the question nor in any
    chunk sent to the LLM — i.e. invented ("134,8 Milliarden" with a real
    course PDF as source). Links (pluginfile/course URLs) are ignored.
    """
    text = re.sub(r"\(https?://[^)]*\)|https?://\S+", " ", answer or "")
    known = _numbers(question)
    for c in chunks:
        known |= _numbers(c.get("text", ""))
    return sorted(n for n in _numbers(text) if n not in known)


def opens_with_not_covered(answer: str) -> bool:
    return bool(_NOT_COVERED.search((answer or "")[:300]))


_SOURCE_LINE = re.compile(r"^\s*(source|sources|quelle|quellen|источник)\b.*$", re.I | re.M)


def strip_source_line(answer: str) -> str:
    return _SOURCE_LINE.sub("", answer or "").strip()


def parse_judge(raw: str) -> tuple[str, str]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw or "", re.S)
        data = json.loads(m.group(0)) if m else {}
    verdict = str(data.get("verdict", "")).lower().strip()
    if verdict not in VERDICT_POINTS:
        return "error", f"unparseable judge output: {raw[:200]!r}"
    return verdict, str(data.get("reason", ""))


def scope_label(scope: dict) -> str:
    if scope["mode"] == "course":
        return f"course {scope['course_id']}"
    return scope["mode"]


# ─────────────────────────────────────────
# Runner
# ─────────────────────────────────────────

def load_env_file() -> None:
    """
    settings.py reads ".env" relative to the CURRENT folder. The backend is
    not always started from api/ (e.g. `uvicorn api.main:app` from the repo
    root, .env lying there), so look in both places and put the values into
    os.environ — pydantic-settings reads environment variables as well.
    Values already set in the environment win.
    """
    import os

    api_dir = Path(__file__).resolve().parent.parent
    candidates = [Path.cwd() / ".env", api_dir / ".env", api_dir.parent / ".env"]
    env_path = next((p for p in candidates if p.is_file()), None)
    if env_path is None:
        sys.exit(
            "No .env found. Looked in:\n  " + "\n  ".join(str(p) for p in candidates)
            + "\nPut the backend's .env into one of these folders."
        )
    print(f"Using {env_path}")
    for line in env_path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        else:
            value = value.split(" #", 1)[0].strip()
        os.environ.setdefault(key, value)


class Evaluator:
    def __init__(self, args):
        # Heavy imports only here, so --help works without .env / models.
        load_env_file()
        from settings import settings
        from llm.factory import create_llm
        from translation.translator import Translator
        from rag.vector_store import VectorStore
        from rag.retriever import Retriever
        from chatbot.services.ai_service import AIService, _detect_language_code
        from chatbot.course_links import format_course_link, build_course_links
        from rag.embeddings import EmbeddingModel

        self.args = args
        self.AIService = AIService
        self.detect_language = _detect_language_code
        self.format_course_link = format_course_link
        self.build_course_links = build_course_links

        print("Loading embedding model and Chroma ...")
        t = time.perf_counter()
        self.store = VectorStore(embedding_model=EmbeddingModel())
        print(f"  done in {time.perf_counter() - t:.1f}s; collections: {sorted(self.store.list_collections())}")

        self.llm = create_llm(model=args.answer_model or None)
        self.translator = None if args.no_retrieval_translation else Translator(llm=self.llm)
        self.answer_model = self.llm.model
        # The judge stays on the .env model even when --answer-model changes
        # the chatbot's model, so runs with different chatbot models are
        # graded by the same judge and stay comparable.
        self.judge_model = args.judge_model or settings.MISTRAL_MODEL

        class RecordingRetriever(Retriever):
            """The production Retriever, remembering what each search returned."""

            def __init__(self, *a, **kw):
                super().__init__(*a, **kw)
                self.calls = []

            def retrieve(self, query, collection_name, *a, **kw):
                result = super().retrieve(query, collection_name, *a, **kw)
                self.calls.append({"query": query, "chunks": result})
                return result

            def retrieve_global(self, query, course_ids, *a, **kw):
                result = super().retrieve_global(query, course_ids, *a, **kw)
                self.calls.append({"query": query, "chunks": result})
                return result

        self.RecordingRetriever = RecordingRetriever
        self._sources_cache: dict[str, list[str]] = {}

    # ── scope → the same arguments MessageService passes ──

    def scope_args(self, scope: dict, course_names: dict[int, str]) -> dict:
        if scope["mode"] == "course":
            cid = scope["course_id"]
            return {
                "collection_name": f"course_{cid}",
                "course_ids": None,
                "course_link": self.format_course_link(cid, course_names.get(cid)),
                "course_links": None,
            }
        if scope["mode"] == "global":
            ids = scope["course_ids"]
            return {
                "collection_name": None,
                "course_ids": ids,
                "course_link": None,
                "course_links": self.build_course_links({c: course_names.get(c) for c in ids}),
            }
        return {"collection_name": None, "course_ids": None, "course_link": None, "course_links": None}

    @staticmethod
    def scope_collections(scope: dict) -> list[str]:
        if scope["mode"] == "course":
            return [f"course_{scope['course_id']}"]
        if scope["mode"] == "global":
            return [f"course_{c}" for c in scope["course_ids"]]
        return []

    def indexed_chunks(self, collection: str) -> list[dict]:
        """All chunks of a collection: [{"source", "text"}] (cached)."""
        if collection not in self._sources_cache:
            chunks = []
            if self.store.collection_exists(collection):
                got = self.store.get_or_create_collection(collection).get(include=["metadatas", "documents"])
                chunks = [
                    {"source": (m or {}).get("source", ""), "text": t or ""}
                    for m, t in zip(got["metadatas"], got["documents"])
                ]
            self._sources_cache[collection] = chunks
        return self._sources_cache[collection]

    def is_target(self, q: dict, chunk_source: str | None, chunk_text: str | None) -> bool:
        """The chunk that answers q: right PDF (if known) AND the evidence text."""
        if q["source_key"] and not matches(chunk_source, q["source_key"]):
            return False
        return has_evidence(chunk_text, q["evidence"])

    def diagnose_miss(self, q: dict, query: str) -> dict:
        """
        Why the answer chunk was not among the chunks sent to the LLM:
          pdf_not_indexed        the PDF is not in this scope's index at all
          evidence_not_in_index  PDF indexed, but no chunk contains the answer text
                                 (image/table in the PDF, extraction or chunking
                                 problem — or the evidence regex is too strict)
          below_min_score        found in a deeper search, score < min_score
          outside_top_n          found, score ok, but n_results other chunks won
          not_in_topN            indexed, but not even in the deep search
        """
        collections = self.scope_collections(q["scope"])
        all_chunks = [c for col in collections for c in self.indexed_chunks(col)]
        if q["source_key"] and not any(matches(c["source"], q["source_key"]) for c in all_chunks):
            return {"diagnosis": "pdf_not_indexed", "deep_rank": None, "deep_score": None}
        if not any(self.is_target(q, c["source"], c["text"]) for c in all_chunks):
            return {"diagnosis": "evidence_not_in_index", "deep_rank": None, "deep_score": None}

        kw = []
        for c in collections:
            kw.extend(self.store.keyword_search(c, query, n_results=self.args.deep_n))
        kw.sort(key=lambda r: r["bm25"], reverse=True)
        kw_rank = next(
            (i for i, r in enumerate(kw, 1) if self.is_target(q, r["metadata"].get("source"), r["text"])),
            None,
        )

        deep = []
        for c in collections:
            deep.extend(self.store.search(collection_name=c, query=query, n_results=self.args.deep_n))
        deep.sort(key=lambda r: r["score"], reverse=True)
        for rank, r in enumerate(deep, 1):
            if self.is_target(q, r["metadata"].get("source"), r["text"]):
                below = r["score"] < self.args.min_score
                return {
                    "diagnosis": "below_min_score" if below else "outside_top_n",
                    "deep_rank": rank,
                    "deep_score": r["score"],
                    "kw_rank": kw_rank,
                }
        return {"diagnosis": f"not_in_top{self.args.deep_n}", "deep_rank": None, "deep_score": None,
                "kw_rank": kw_rank}

    async def judge(self, q: dict, answer: str) -> tuple[str, str]:
        if q.get("key_facts"):
            return await self.judge_facts(q, answer)
        messages = [
            {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
            {"role": "user", "content": (
                f"GROUP: {q['group']}\n\nQUESTION:\n{q['question']}\n\n"
                f"EXPECTED:\n{q['expected']}\n\nACTUAL ANSWER:\n{answer}"
            )},
        ]
        kwargs = {"temperature": 0, "response_format": {"type": "json_object"}}
        kwargs["model"] = self.judge_model
        raw = await with_retry(lambda: self.llm.chat(messages, **kwargs), f"judge #{q['id']}")
        return parse_judge(raw)

    async def judge_facts(self, q: dict, answer: str) -> tuple[str, str]:
        """One call, every key fact checked separately; verdict computed here."""
        facts = q["key_facts"]
        listed = "\n".join(f"{i}. {f}" for i, f in enumerate(facts, 1))
        messages = [
            {"role": "system", "content": FACTS_JUDGE_PROMPT},
            {"role": "user", "content": f"QUESTION:\n{q['question']}\n\nANSWER:\n{answer}\n\nKEY FACTS:\n{listed}"},
        ]
        kwargs = {"temperature": 0, "response_format": {"type": "json_object"},
                  "model": self.judge_model}
        raw = await with_retry(lambda: self.llm.chat(messages, **kwargs), f"judge #{q['id']}")
        try:
            parsed = json.loads(raw)
            items = parsed.get("facts", [])
            claims_not_covered = bool(parsed.get("claims_not_covered"))
        except (json.JSONDecodeError, AttributeError):
            return "error", f"unparseable judge output: {raw[:200]!r}"

        present = {}
        for it in items:
            try:
                present[int(it.get("n"))] = bool(it.get("present"))
            except (TypeError, ValueError):
                continue
        # Numeric safety net: the judge sometimes misses a number in an
        # answer in another language (#27: "360 тонн в год" -> "absent").
        # If every number of a fact appears in the answer and at least one
        # of them has 3+ digits (too specific to be a coincidence), count it.
        answer_numbers = set(re.findall(r"\d+", re.sub(r"(?<=\d)[.,](?=\d{3}\b)", "", answer)))
        for i, f in enumerate(facts, 1):
            if present.get(i):
                continue
            nums = re.findall(r"\d+", re.sub(r"(?<=\d)[.,](?=\d{3}\b)", "", f))
            if nums and any(len(n) >= 3 for n in nums) and all(n in answer_numbers for n in nums):
                present[i] = True

        missing = [f for i, f in enumerate(facts, 1) if not present.get(i)]
        found = len(facts) - len(missing)
        if found == len(facts):
            verdict = "correct"
        elif found * 2 >= len(facts) and found > 0:
            verdict = "partial"
        else:
            verdict = "wrong"
        reason = f"{found}/{len(facts)} key facts" + (f"; missing: {'; '.join(missing)}" if missing else "")

        # "I don't see this in your materials ... (then the right answer)":
        # confusing for the student even if the facts are there.
        if (claims_not_covered or opens_with_not_covered(answer)) and found > 0:
            verdict = "partial" if verdict == "correct" else verdict
            reason = "CONTRADICTION: says not covered but answers; " + reason
        return verdict, reason

    async def run_question(self, q: dict, course_names: dict[int, str], history: list[dict]) -> dict:
        args = self.args
        retriever = self.RecordingRetriever(
            vector_store=self.store, min_score=args.min_score, hybrid=not args.no_hybrid
        )
        ai = self.AIService(
            llm=self.llm,
            retriever=retriever,
            translator=self.translator,
            retrieval_n_results=args.n_results,
        )
        scope_kw = self.scope_args(q["scope"], course_names)
        messages = history + [{"role": "user", "content": q["question"]}]

        res = {
            "base_id": q.get("base_id"),
            "id": q["id"], "group": q["group"], "scope": scope_label(q["scope"]), "lang": q["lang"],
            "question": q["question"], "expected": q["expected"],
            "retrieval_check": q["retrieval_check"], "manual_right": q["manual"]["right"],
        }
        t0 = time.perf_counter()
        answer = None

        if args.retrieval_only:
            # Same first steps generate_response() does, without the answer call.
            rq = ai._build_retrieval_query(messages)
            last = ai._get_last_user_message(messages)
            await ai._build_system_prompt_with_fallback(rq, last, **scope_kw)
        else:
            answer = await with_retry(
                lambda: ai.generate_response(messages, **scope_kw), f"answer #{q['id']}"
            )
        res["total_ms"] = round((time.perf_counter() - t0) * 1000)

        # ── 1. retrieval ──
        used = retriever.calls[-1] if retriever.calls else {"query": None, "chunks": []}
        chunks = used["chunks"]
        res["search_query"] = used["query"]
        res["n_chunks"] = len(chunks)
        res["top_source"] = chunks[0]["metadata"].get("source") if chunks else None
        res["top_score"] = chunks[0]["score"] if chunks else None
        res["rank"] = res["score_expected"] = None
        res["diagnosis"] = res["deep_rank"] = res["deep_score"] = None

        res["source_in_context"] = None
        if q["retrieval_check"] == "hit":
            res["source_in_context"] = any(
                matches(c["metadata"].get("source"), q["source_key"]) for c in chunks
            )
            for rank, c in enumerate(chunks, 1):
                if self.is_target(q, c["metadata"].get("source"), c["text"]):
                    res["rank"], res["score_expected"] = rank, c["score"]
                    break
            res["retrieval_ok"] = res["rank"] is not None
            if not res["retrieval_ok"]:
                res.update(self.diagnose_miss(q, used["query"] or q["question"]))
        elif q["retrieval_check"] == "no_context":
            res["retrieval_ok"] = not chunks
        else:
            res["retrieval_ok"] = None

        # ── 2./3. answer ──
        res["answer"] = answer
        res["verdict"] = res["judge_reason"] = None
        res["lang_detected"] = res["lang_ok"] = res["cites_expected"] = None
        res["ungrounded_numbers"] = None
        if answer is not None:
            # Only meaningful when course chunks were the basis of the answer.
            if chunks:
                res["ungrounded_numbers"] = ", ".join(ungrounded_numbers(answer, q["question"], chunks)) or None
            detected = self.detect_language(strip_source_line(answer))
            res["lang_detected"] = detected
            res["lang_ok"] = None if detected is None else detected == q["lang"]
            if q["source_key"]:
                res["cites_expected"] = q["source_key"] in normalize(answer)
            if q["retrieval_check"] == "no_context":
                # Not enrolled: general-knowledge answers are allowed, course
                # content is not. The LLM judge cannot tell the two apart
                # (it graded every general answer "wrong"), so decide by rule:
                # no chunk reached the LLM and no course PDF is cited.
                leaked = bool(chunks) or bool(re.search(r"\.pdf\b", answer, re.I))
                res["verdict"] = "wrong" if leaked else "correct"
                res["judge_reason"] = "rule: course content reached the answer" if leaked \
                    else "rule: no course chunks, no course PDF cited"
            elif not args.no_judge:
                res["verdict"], res["judge_reason"] = await self.judge(q, answer)

        return res


# ─────────────────────────────────────────
# Reporting
# ─────────────────────────────────────────

CSV_FIELDS = [
    "id", "base_id", "group", "scope", "lang", "question",
    "retrieval_check", "retrieval_ok", "source_in_context", "rank", "score_expected", "diagnosis", "deep_rank", "deep_score", "kw_rank",
    "top_source", "top_score", "n_chunks",
    "verdict", "judge_reason", "manual_right", "lang_detected", "lang_ok", "cites_expected", "ungrounded_numbers",
    "total_ms", "search_query", "expected", "answer", "error",
]


def count(results, key, value=True):
    return sum(1 for r in results if r.get(key) == value)


def print_summary(results: list[dict], config: dict) -> dict:
    n = len(results)
    summary = {"n": n}

    print("\n" + "=" * 72)
    print(f"RUN: {config['label'] or '-'}   model={config.get('answer_model')}   n_results={config['n_results']}  min_score={config['min_score']}  "
          f"retrieval_translation={not config['no_retrieval_translation']}  hybrid={config.get('hybrid', False)}  "
          f"as_chats={config['as_chats']}")
    print("=" * 72)

    errors = [r for r in results if r.get("error")]
    if errors:
        print(f"ERRORS: {len(errors)} questions failed: " + ", ".join(f"#{r['id']}" for r in errors))

    hit_rows = [r for r in results if r.get("retrieval_check") == "hit" and not r.get("error")]
    nc_rows = [r for r in results if r.get("retrieval_check") == "no_context" and not r.get("error")]
    hits = count(hit_rows, "retrieval_ok")
    summary["retrieval_hit"] = f"{hits}/{len(hit_rows)}"
    print(f"Retrieval  : answer chunk in context {hits}/{len(hit_rows)}"
          f"   | right PDF in context {count(hit_rows, 'source_in_context')}/{len(hit_rows)}"
          f"   | no-access checks {count(nc_rows, 'retrieval_ok')}/{len(nc_rows)}")

    langs = sorted({r["lang"] for r in hit_rows})
    if len(langs) > 1:
        print("   by language: " + "   ".join(
            f"{lg} {count([r for r in hit_rows if r['lang'] == lg], 'retrieval_ok')}"
            f"/{len([r for r in hit_rows if r['lang'] == lg])}" for lg in langs
        ))

    judged = [r for r in results if r.get("verdict") in VERDICT_POINTS]
    if judged:
        points = sum(VERDICT_POINTS[r["verdict"]] for r in judged)
        summary["answer_score"] = round(points / len(judged), 3)
        print(f"Answers    : correct {count(judged, 'verdict', 'correct')}, "
              f"partial {count(judged, 'verdict', 'partial')}, wrong {count(judged, 'verdict', 'wrong')}"
              f"  of {len(judged)}   → score {points:.1f}/{len(judged)} ({100 * points / len(judged):.0f}%)")
        groups = sorted({r["group"] for r in judged})
        for g in groups:
            rows = [r for r in judged if r["group"] == g]
            p = sum(VERDICT_POINTS[r["verdict"]] for r in rows)
            print(f"   {g:<16} {p:.1f}/{len(rows)}")

    lang_rows = [r for r in results if r.get("lang_ok") is not None]
    if lang_rows:
        print(f"Language   : answer in question's language {count(lang_rows, 'lang_ok')}/{len(lang_rows)}")
    cite_rows = [r for r in results if r.get("cites_expected") is not None and r.get("group") != "No answer"]
    if cite_rows:
        print(f"Citation   : expected source named in answer {count(cite_rows, 'cites_expected')}/{len(cite_rows)}")
    times = sorted(r["total_ms"] for r in results if r.get("total_ms"))
    invented = [r for r in results if r.get("ungrounded_numbers")]
    checked = [r for r in results if r.get("answer") and r.get("n_chunks")]
    if checked:
        print(f"Invented # : answers with numbers not in the materials {len(invented)}/{len(checked)}")
    if times:
        print(f"Time       : median {times[len(times) // 2]} ms, max {times[-1]} ms per question")

    problems = [
        r for r in results
        if r.get("error") or r.get("retrieval_ok") is False
        or r.get("verdict") in ("wrong", "partial", "error") or r.get("lang_ok") is False
        or r.get("ungrounded_numbers")
    ]
    if problems:
        print("\nProblems:")
        for r in problems:
            parts = []
            if r.get("error"):
                parts.append(f"ERROR {r['error']}")
            if r.get("retrieval_ok") is False:
                if r["retrieval_check"] == "no_context":
                    parts.append(f"LEAK: {r['n_chunks']} chunks for a non-enrolled user")
                else:
                    deep = f", vector rank {r['deep_rank']} score {r['deep_score']}" if r.get("deep_rank") else ""
                    if r.get("diagnosis") not in ("pdf_not_indexed", "evidence_not_in_index"):
                        deep += f", keyword rank {r.get('kw_rank') or 'none'}"
                    parts.append(f"retrieval MISS ({r['diagnosis']}{deep})")
            if r.get("verdict") in ("wrong", "partial", "error"):
                parts.append(f"answer {r['verdict'].upper()}: {r.get('judge_reason')}")
            if r.get("lang_ok") is False:
                parts.append(f"language {r['lang_detected']} ≠ {r['lang']}")
            if r.get("ungrounded_numbers"):
                parts.append(f"NUMBERS NOT IN MATERIALS: {r['ungrounded_numbers']}")
            print(f"  #{r['id']:<3}[{r['group']}, {r['scope']}, {r['lang']}] " + " | ".join(parts))
    return summary


def compare_with(previous_path: Path, results: list[dict]) -> None:
    prev = json.loads(previous_path.read_text(encoding="utf-8"))
    before = {r["id"]: r for r in prev["results"]}
    print(f"\nCompared with {previous_path.parent.name} ({prev['config'].get('label') or '-'}):")
    print(f"   before: {prev.get('summary', {})}")

    changes = []
    for r in results:
        b = before.get(r["id"])
        if not b:
            continue
        if b.get("retrieval_ok") is not None and r.get("retrieval_ok") is not None \
                and b["retrieval_ok"] != r["retrieval_ok"]:
            changes.append(f"#{r['id']} retrieval {'MISS→hit' if r['retrieval_ok'] else 'hit→MISS'}")
        bv, rv = b.get("verdict"), r.get("verdict")
        if bv in VERDICT_POINTS and rv in VERDICT_POINTS and bv != rv:
            better = VERDICT_POINTS[rv] > VERDICT_POINTS[bv]
            changes.append(f"#{r['id']} answer {bv}→{rv} {'✓' if better else '✗'}")
    print("   " + ("\n   ".join(changes) if changes else "no per-question changes"))


def write_outputs(out_dir: Path, results: list[dict], config: dict, summary: dict) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "results.json").write_text(
        json.dumps({"config": config, "summary": summary, "results": results}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    # ";" + BOM: opens correctly in a German-locale Excel by double-click.
    with open(out_dir / "results.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS, delimiter=";", extrasaction="ignore")
        w.writeheader()
        w.writerows(results)
    print(f"\nSaved: {out_dir / 'results.json'}\n       {out_dir / 'results.csv'}")


def latest_previous_run(exclude: Path | None = None) -> Path | None:
    if not RESULTS_DIR.exists():
        return None
    runs = sorted(
        p / "results.json" for p in RESULTS_DIR.iterdir()
        if p.is_dir() and not p.name.startswith("judge_") and (p / "results.json").exists() and p != exclude
    )
    return runs[-1] if runs else None


# ─────────────────────────────────────────
# Modes
# ─────────────────────────────────────────

async def run_eval(args, questions, course_names) -> None:
    ev = Evaluator(args)
    sem = asyncio.Semaphore(args.concurrency)
    results: list[dict] = []
    done = 0

    async def guarded(q, history):
        nonlocal done
        try:
            r = await ev.run_question(q, course_names, history)
        except Exception as e:
            r = {"id": q["id"], "group": q["group"], "scope": scope_label(q["scope"]), "lang": q["lang"],
                 "question": q["question"], "retrieval_check": q["retrieval_check"], "error": repr(e)}
        done += 1
        mark = {True: "hit", False: "MISS", None: "-"}[r.get("retrieval_ok")]
        print(f"  [{done}/{len(questions)}] #{q['id']:<3} retrieval={mark:<4} verdict={r.get('verdict') or '-':<8} "
              f"{r.get('total_ms', '?')} ms")
        return r

    async def one(q):
        async with sem:
            return await guarded(q, [])

    async def chat(chat_questions):
        async with sem:
            history, out = [], []
            for q in chat_questions:
                r = await guarded(q, history)
                out.append(r)
                history = history + [{"role": "user", "content": q["question"]}]
                if r.get("answer"):
                    history.append({"role": "assistant", "content": r["answer"]})
            return out

    print(f"Running {len(questions)} questions (concurrency {args.concurrency}) ...")
    t = time.perf_counter()
    if args.as_chats:
        chats: dict[str, list] = {}
        for q in questions:
            chats.setdefault(q["chat"], []).append(q)
        for chunk in await asyncio.gather(*(chat(cq) for cq in chats.values())):
            results.extend(chunk)
    else:
        results = list(await asyncio.gather(*(one(q) for q in questions)))
    results.sort(key=lambda r: r["id"])
    print(f"Finished in {time.perf_counter() - t:.0f}s")

    config = {
        "label": args.label, "started": datetime.now().isoformat(timespec="seconds"),
        "n_results": args.n_results, "min_score": args.min_score,
        "no_retrieval_translation": args.no_retrieval_translation, "as_chats": args.as_chats,
        "hybrid": not args.no_hybrid,
        "retrieval_only": args.retrieval_only, "answer_model": ev.answer_model,
        "judge_model": ev.judge_model,
        "answer_model_override": args.answer_model,
        "only": args.only, "group": args.group,
    }
    summary = print_summary(results, config)

    previous = Path(args.compare) if args.compare else latest_previous_run()
    if previous and not args.no_compare:
        compare_with(previous, results)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = stamp + (f"_{re.sub(r'[^A-Za-z0-9_-]', '', args.label)}" if args.label else "")
    write_outputs(RESULTS_DIR / name, results, config, summary)


async def run_judge_calibration(args, questions) -> None:
    """
    Grades the answers RECORDED in the sheet (column H) and compares the
    judge with your manual "Right?" column. Shows how far the automatic
    verdict can be trusted before relying on it.
    """
    ev = Evaluator(args)
    manual_to_verdict = {"yes": "correct", "no": "wrong"}
    sem = asyncio.Semaphore(args.concurrency)

    async def one(q):
        async with sem:
            answer = q["manual"]["answer"]
            if not answer or q["retrieval_check"] == "no_context":
                return None  # unenrolled rows are graded by rule, not by the judge
            verdict, reason = await ev.judge(q, answer)
            manual = str(q["manual"]["right"] or "").strip().lower()
            return {"id": q["id"], "group": q["group"], "manual": manual, "verdict": verdict, "reason": reason}

    rows = [r for r in await asyncio.gather(*(one(q) for q in questions)) if r]
    rows.sort(key=lambda r: r["id"])
    clear = [r for r in rows if r["manual"] in manual_to_verdict]
    agree = [r for r in clear if manual_to_verdict[r["manual"]] == r["verdict"]]

    print(f"\nJudge vs manual: agrees on {len(agree)}/{len(clear)} clear Yes/No labels")
    for r in rows:
        expected = manual_to_verdict.get(r["manual"])
        if expected != r["verdict"]:
            tag = "unsure" if expected is None else "DISAGREE"
            print(f"  #{r['id']:<3}[{r['group']}] manual={r['manual'] or '-':<8} judge={r['verdict']:<8} {tag}: {r['reason']}")

    out = RESULTS_DIR / f"judge_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    out.mkdir(parents=True, exist_ok=True)
    (out / "judge_calibration.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved: {out / 'judge_calibration.json'}")


def main() -> None:
    # A crash inside native code (torch, chromadb) kills Python without a
    # traceback; faulthandler still prints where it happened.
    import faulthandler
    faulthandler.enable()

    # Windows console: avoid UnicodeEncodeError on umlauts / Cyrillic.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass

    p = argparse.ArgumentParser(description="SDG Campus chatbot quality test")
    p.add_argument("--only", help="comma-separated question ids, e.g. 5,13,27")
    p.add_argument("--group", help="only one group: Factual, Cross-language, Access/Scope, 'No answer'")
    p.add_argument("--retrieval-only", action="store_true", help="skip answer + judge (fast, almost no LLM cost)")
    p.add_argument("--no-judge", action="store_true", help="generate answers but do not grade them")
    p.add_argument("--judge-only", action="store_true", help="grade the sheet's recorded answers, compare with manual labels")
    p.add_argument("--as-chats", action="store_true", help="replay questions in chat order with history")
    p.add_argument("--n-results", type=int, default=12, help="chunks sent to the LLM (production: 12)")
    p.add_argument("--min-score", type=float, default=0.3, help="retriever min_score (production: 0.3)")
    p.add_argument("--no-retrieval-translation", action="store_true", help="do not translate non-EN/DE search queries")
    p.add_argument("--no-hybrid", action="store_true", help="vector search only (no BM25 keyword search)")
    p.add_argument("--deep-n", type=int, default=60, help="how deep to look when diagnosing a retrieval miss")
    p.add_argument("--answer-model",
                   help="Mistral model the CHATBOT answers with (default: MISTRAL_MODEL from .env)")
    p.add_argument("--judge-model",
                   help="Mistral model for the judge (default: the chatbot's MISTRAL_MODEL). "
                        "Must be available in your Mistral subscription.")
    p.add_argument("--concurrency", type=int, default=3, help="questions in parallel (Mistral rate limit!)")
    p.add_argument("--label", default="", help="name for this run, e.g. 'n8' or 'after-chunking-fix'")
    p.add_argument("--compare", help="results.json to compare with (default: latest run)")
    p.add_argument("--no-compare", action="store_true")
    args = p.parse_args()

    questions, course_names = load_dataset()
    if args.only:
        ids = {int(x) for x in args.only.split(",") if x.strip()}
        questions = [q for q in questions if q["id"] in ids]
    if args.group:
        questions = [q for q in questions if q["group"].lower() == args.group.lower()]
    if not questions:
        sys.exit("No questions selected.")

    if args.judge_only:
        asyncio.run(run_judge_calibration(args, questions))
    else:
        asyncio.run(run_eval(args, questions, course_names))


if __name__ == "__main__":
    main()
    