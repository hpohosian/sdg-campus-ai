"""
Measures how long translating a whole chat takes (what the student waits
for after switching the chat language).

Reads one chat from the chat database (PostgreSQL must be running — the
Docker "db" service), translates its messages exactly like the backend
does (all messages in parallel) and prints the wall time. Writes NOTHING:
no translation cache, no messages. FastAPI does not need to run.

Run from the api/ folder:

    python -m eval.bench_translation                       # longest chat, to Russian
    python -m eval.bench_translation --session <id> --to en
    python -m eval.bench_translation --mode whole          # old behaviour: one call per message
    python -m eval.bench_translation --model mistral-small-latest
    python -m eval.bench_translation --show 2              # print 2 translated messages to check quality

--mode pieces (default) is the new behaviour: long messages are cut at
paragraphs and the pieces are translated in parallel.
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

    p = argparse.ArgumentParser(description="Chat translation benchmark")
    p.add_argument("--session", help="session id (default: the chat with the most text)")
    p.add_argument("--to", default="ru", help="target language code: en, de, ru, uk (default ru)")
    p.add_argument("--mode", choices=["pieces", "whole"], default="pieces")
    p.add_argument("--model", help="Mistral model (default: TRANSLATION_MODEL or MISTRAL_MODEL)")
    p.add_argument("--concurrency", type=int, default=12, help="messages in parallel (backend: 12)")
    p.add_argument("--show", type=int, default=0, help="print the N longest translated messages")
    args = p.parse_args()

    load_env_file()
    from sqlalchemy import func, select

    from settings import settings
    from db.connection import ChatSessionLocal
    from db.models.message import MessageModel
    from chatbot.repositories.message_repository import MessageRepository
    from chatbot.services.ai_service import _detect_language_code
    from llm.factory import create_llm
    from translation.translator import Translator

    db = ChatSessionLocal()
    try:
        session_id = args.session
        if not session_id:
            session_id = db.execute(
                select(MessageModel.session_id)
                .where(MessageModel.is_active == 1)
                .group_by(MessageModel.session_id)
                .order_by(func.sum(func.length(MessageModel.content)).desc())
                .limit(1)
            ).scalar()
            if not session_id:
                sys.exit("No chats in the database.")
        messages = MessageRepository(db).get_active_thread(session_id)
    finally:
        db.close()

    if not messages:
        sys.exit(f"Session {session_id} has no messages.")

    model = args.model or settings.TRANSLATION_MODEL or settings.MISTRAL_MODEL
    translator = Translator(llm=create_llm(), model=model)
    if args.mode == "whole":
        translator.PIECE_CHARS = 10 ** 9   # never split = old behaviour

    total_chars = sum(len(m.content) for m in messages)
    longest = max(len(m.content) for m in messages)
    print(f"session {session_id}: {len(messages)} messages, {total_chars} chars (longest {longest})")
    print(f"target={args.to}  mode={args.mode}  model={model}  concurrency={args.concurrency}\n")

    sem = asyncio.Semaphore(args.concurrency)
    skipped = 0

    async def one(m):
        nonlocal skipped
        async with sem:
            t = time.perf_counter()
            if _detect_language_code(m.content) == args.to:
                skipped += 1
                return m, m.content, 0.0, "skipped (already in target language)"
            try:
                out = await translator.translate(m.content, args.to)
                return m, out, time.perf_counter() - t, ""
            except Exception as e:
                return m, m.content, time.perf_counter() - t, f"ERROR {e!r}"

    t0 = time.perf_counter()
    rows = await asyncio.gather(*(one(m) for m in messages))
    wall = time.perf_counter() - t0

    for m, _out, secs, note in rows:
        print(f"  #{m.id:<6} {m.role:<9} {len(m.content):>5} chars  {secs:5.1f} s  {note}")
    print(f"\nTOTAL (what the student waits): {wall:.1f} s   | skipped {skipped}/{len(messages)}")

    if args.show:
        print("\n" + "=" * 72)
        for m, out, _secs, _note in sorted(rows, key=lambda r: len(r[0].content), reverse=True)[: args.show]:
            print(f"--- #{m.id} ORIGINAL ---\n{m.content}\n\n--- #{m.id} TRANSLATED ---\n{out}\n")


if __name__ == "__main__":
    asyncio.run(main())
    