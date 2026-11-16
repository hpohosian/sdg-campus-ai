"""
Try the quiz generator from the command line (development, no Moodle).

Run from the api/ folder (like the other eval scripts):

    python -m eval.quiz_try 12                          # 5 questions, whole course 12
    python -m eval.quiz_try 12 --topic "PtL-Anlagen"    # about a topic
    python -m eval.quiz_try 12 --count 10 --lang ru
    python -m eval.quiz_try 12 --chat "Wie läuft eine Zukunftswerkstatt ab?"   # scope "chat"
    python -m eval.quiz_try 12 --out quiz.json          # also save the JSON
"""

import argparse
import asyncio
import sys
import time

from eval.run_eval import load_env_file


async def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass

    p = argparse.ArgumentParser(description="Generate a quiz (development)")
    p.add_argument("course_ids", nargs="+", type=int)
    p.add_argument("--count", type=int, default=5)
    p.add_argument("--lang", default="de")
    p.add_argument("--topic", default=None)
    p.add_argument("--chat", default=None, help="chat text -> scope 'chat'")
    p.add_argument("--out", default="", help="save the quiz JSON to this file")
    args = p.parse_args()

    load_env_file()
    from settings import settings
    from llm.factory import create_llm
    from rag.embeddings import EmbeddingModel
    from rag.retriever import Retriever
    from rag.vector_store import VectorStore
    from chatbot.quiz.generator import QuizGenerator

    store = VectorStore(embedding_model=EmbeddingModel())
    generator = QuizGenerator(
        llm=create_llm(),
        retriever=Retriever(vector_store=store, min_score=0.3),
        model=settings.QUIZ_MODEL or None,
    )
    t = time.perf_counter()
    quiz = await generator.generate(
        course_ids=args.course_ids,
        count=args.count,
        language=args.lang,
        scope="chat" if args.chat else "course",
        topic=args.topic,
        chat_text=args.chat,
    )
    print(f"\n{len(quiz.questions)} questions in {time.perf_counter() - t:.1f}s "
          f"(scope={quiz.scope}, topic={quiz.topic!r}, language={quiz.language})\n")
    for n, q in enumerate(quiz.questions, 1):
        print(f"{n}. {q.question}")
        for i, option in enumerate(q.options):
            print(f"   {'*' if i in q.correct else ' '} {'ABCD'[i]}) {option}")
        print(f"   -> {q.explanation}")
        print(f"   source: {q.source}" + (f" (page {q.page})" if q.page else "") + "\n")
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(quiz.model_dump_json(indent=2))
        print(f"saved to {args.out}")


if __name__ == "__main__":
    asyncio.run(main())
