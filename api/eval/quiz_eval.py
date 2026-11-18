"""
Quality test for generated quizzes (step 4 of the quiz plan).

For every course it generates quizzes with the real generator, then checks
every question:

  Judge (LLM, sees ONLY the material block the question was made from):
    - answers the question itself, without seeing which option is marked
      right ("blind") -> must pick the same option as the generator;
    - "several": more than one option is right according to the block
      (ambiguous question);
    - "none": no option follows from the block (made-up question/answer);
    - about_subject: the question is about the subject, not about the
      course organisation, file names or the like.

  Deterministic:
    - the right option is the longest one (a student could guess it by its
      form; with 4 options ~25 % is chance, much more is a problem);
    - mentions of internal block numbers, duplicate questions, missing source.

Run from the api/ folder:

    python -m eval.quiz_eval                      # all courses, 1 quiz x 5 questions, German
    python -m eval.quiz_eval 8 12 --quizzes 2     # courses 8 and 12, 2 quizzes each
    python -m eval.quiz_eval --lang ru --count 10
    python -m eval.quiz_eval --topic "Zukunftswerkstatt" 8

Results: eval/results/quiz_<timestamp>/results.json (every question with
its block, the judge's answer and the problems found).
"""

import argparse
import asyncio
import json
import re
import sys
import time
from datetime import datetime

from eval.run_eval import RESULTS_DIR, load_env_file, with_retry


JUDGE_PROMPT = """You check a multiple-choice quiz question that was written from a piece of course material.

You get the MATERIAL and the QUESTION with options A-D. You are NOT told which option is meant to be right.

1. Decide from the MATERIAL alone which option(s) are correct. Use only the material, no outside knowledge.
2. Decide whether the question is about the subject matter (concepts, facts, reasons) — "false" if it is about the organisation of a course (hours, dates, who teaches, how results are handed in), file names, page numbers or the document itself.

Answer with JSON only:
{"correct": ["B"], "about_subject": true, "note": "one short sentence, only if something is wrong"}

"correct": the letter(s) the material supports. Several letters if several options are right according to the material. [] if no option follows from the material."""

LETTERS = "ABCD"
_BLOCK_WORD = re.compile(r"\b(?:block|блок[а-яё]*)\s*\d+", re.IGNORECASE)


async def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass

    p = argparse.ArgumentParser(description="Quality test for generated quizzes")
    p.add_argument("course_ids", nargs="*", type=int, help="default: all indexed courses")
    p.add_argument("--quizzes", type=int, default=1, help="quizzes per course")
    p.add_argument("--count", type=int, default=5, help="questions per quiz (3, 5, 10, 20)")
    p.add_argument("--lang", default="de")
    p.add_argument("--topic", default=None)
    p.add_argument("--judge-model", default=None, help="default: MISTRAL_MODEL")
    p.add_argument("--concurrency", type=int, default=3)
    p.add_argument("--label", default="")
    args = p.parse_args()

    load_env_file()
    from settings import settings
    from llm.factory import create_llm
    from rag.embeddings import EmbeddingModel
    from rag.retriever import Retriever
    from rag.vector_store import VectorStore
    from chatbot.quiz.generator import QuizGenerator

    store = VectorStore(embedding_model=EmbeddingModel())
    llm = create_llm()
    generator = QuizGenerator(
        llm=llm, retriever=Retriever(vector_store=store, min_score=0.3),
        model=settings.QUIZ_MODEL or None,
    )
    judge_model = args.judge_model or settings.MISTRAL_MODEL

    course_ids = args.course_ids or sorted(
        int(n.split("_")[1]) for n in store.list_collections() if n.startswith("course_")
    )
    print(f"Courses {course_ids}, {args.quizzes} quiz(zes) x {args.count} questions, "
          f"language {args.lang}, topic {args.topic!r}, judge {judge_model}\n")

    semaphore = asyncio.Semaphore(args.concurrency)

    async def judge(question, block: str) -> dict:
        options = "\n".join(f"{LETTERS[i]}) {o}" for i, o in enumerate(question.options))
        messages = [
            {"role": "system", "content": JUDGE_PROMPT},
            {"role": "user", "content": f"MATERIAL:\n{block[:4000]}\n\nQUESTION:\n{question.question}\n{options}"},
        ]
        async with semaphore:
            raw = await with_retry(
                lambda: llm.chat(messages, model=judge_model, temperature=0,
                                 response_format={"type": "json_object"}),
                "judge",
            )
        try:
            data = json.loads(re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip()))
        except json.JSONDecodeError:
            return {"error": f"unparseable judge output: {raw[:150]!r}"}
        return data

    results = []
    t_start = time.perf_counter()
    for course_id in course_ids:
        for n in range(args.quizzes):
            t = time.perf_counter()
            try:
                quiz = await generator.generate(
                    course_ids=[course_id], count=args.count, language=args.lang, topic=args.topic,
                )
            except Exception as e:
                print(f"course {course_id} quiz {n + 1}: GENERATION FAILED: {e!r}")
                results.append({"course_id": course_id, "quiz": n + 1, "error": repr(e)})
                continue
            seconds = time.perf_counter() - t

            verdicts = await asyncio.gather(*(
                judge(q, generator.question_blocks.get(q.question, "")) for q in quiz.questions
            ))
            seen = set()
            for i, (q, v) in enumerate(zip(quiz.questions, verdicts), 1):
                marked = LETTERS[q.correct[0]]
                judged = sorted({str(x).strip().upper()[:1] for x in v.get("correct", []) if str(x).strip()})
                problems = []
                if v.get("error"):
                    problems.append(v["error"])
                elif not judged:
                    problems.append("no option follows from the material")
                elif len(judged) > 1:
                    problems.append(f"ambiguous: material supports {', '.join(judged)}")
                elif judged != [marked]:
                    problems.append(f"WRONG KEY: marked {marked}, material supports {judged[0]}")
                if v.get("about_subject") is False:
                    problems.append("not about the subject")
                lengths = [len(o) for o in q.options]
                longest = lengths[q.correct[0]] == max(lengths) and lengths.count(max(lengths)) == 1
                if _BLOCK_WORD.search(" ".join([q.question, q.explanation, *q.options])):
                    problems.append("mentions a block number")
                key = " ".join(q.question.casefold().split())
                if key in seen:
                    problems.append("duplicate question")
                seen.add(key)
                if not q.source:
                    problems.append("no source")
                if not generator.question_blocks.get(q.question):
                    problems.append("(block not found for judging)")

                results.append({
                    "course_id": course_id, "quiz": n + 1, "n": i, "seconds": round(seconds, 1),
                    "question": q.question, "options": q.options, "marked": marked,
                    "judge_correct": judged, "about_subject": v.get("about_subject"),
                    "judge_note": v.get("note", ""), "correct_is_longest": longest,
                    "explanation": q.explanation, "source": q.source,
                    "block": generator.question_blocks.get(q.question, ""), "problems": problems,
                })
            bad = sum(1 for r in results[-len(quiz.questions):] if r["problems"])
            print(f"course {course_id} quiz {n + 1}: {len(quiz.questions)} questions in {seconds:.0f}s, "
                  f"{bad} with problems")

    # ── summary ──
    questions = [r for r in results if "question" in r]
    failed = [r for r in results if "error" in r and "question" not in r]
    total = len(questions) or 1
    key_ok = sum(1 for r in questions if r["judge_correct"] == [r["marked"]])
    wrong_key = sum(1 for r in questions if any(p.startswith("WRONG KEY") for p in r["problems"]))
    ambiguous = sum(1 for r in questions if any(p.startswith("ambiguous") for p in r["problems"]))
    unsupported = sum(1 for r in questions if "no option follows from the material" in r["problems"])
    off_subject = sum(1 for r in questions if r["about_subject"] is False)
    longest = sum(1 for r in questions if r["correct_is_longest"])
    times = sorted(r["seconds"] for r in questions if r["n"] == 1)

    print("\n" + "=" * 72)
    print(f"QUIZ EVAL {args.label or ''}  courses={course_ids}  lang={args.lang}  "
          f"model={settings.QUIZ_MODEL or settings.MISTRAL_MODEL}  judge={judge_model}")
    print("=" * 72)
    print(f"Questions      : {len(questions)}   (quizzes failed: {len(failed)})")
    print(f"Key correct    : {key_ok}/{len(questions)} ({100 * key_ok / total:.0f}%)  "
          f"| wrong key {wrong_key} | ambiguous {ambiguous} | not in material {unsupported}")
    print(f"About subject  : {len(questions) - off_subject}/{len(questions)}")
    print(f"Right=longest  : {longest}/{len(questions)} ({100 * longest / total:.0f}%, chance ~25%)")
    if times:
        print(f"Time per quiz  : median {times[len(times) // 2]:.0f}s, max {times[-1]:.0f}s")

    problems = [r for r in questions if r["problems"]]
    if problems:
        print("\nProblems:")
        for r in problems:
            print(f"  course {r['course_id']} quiz {r['quiz']} Q{r['n']}: {'; '.join(r['problems'])}")
            print(f"     {r['question']}")
            for i, o in enumerate(r["options"]):
                print(f"       {'*' if LETTERS[i] == r['marked'] else ' '} {LETTERS[i]}) {o}")
            if r["judge_note"]:
                print(f"     judge: {r['judge_note']}")

    out = RESULTS_DIR / f"quiz_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps({
        "config": {**vars(args), "model": settings.QUIZ_MODEL or settings.MISTRAL_MODEL, "judge": judge_model},
        "summary": {"questions": len(questions), "key_correct": key_ok, "wrong_key": wrong_key,
                    "ambiguous": ambiguous, "not_in_material": unsupported, "off_subject": off_subject,
                    "correct_is_longest": longest, "failed_quizzes": len(failed)},
        "results": results,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved: {out / 'results.json'}   ({time.perf_counter() - t_start:.0f}s)")


if __name__ == "__main__":
    asyncio.run(main())
