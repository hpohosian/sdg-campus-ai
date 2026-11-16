"""
Shows the table chunks stored in the index (see rag/loaders/pdf_tables.py),
to check whether table detection found real tables.

Run from the api/ folder:

    python -m eval.show_tables 13                  # all tables of course 13
    python -m eval.show_tables 13 --source bpb     # only files whose name contains "bpb"
    python -m eval.show_tables 13 --out tables.txt # write to a file instead

Reads ChromaDB directly (no embedding model, no server needed).
"""

import argparse
import sys

import chromadb
from chromadb.config import Settings as ChromaSettings

from eval.run_eval import load_env_file


def main() -> None:
    p = argparse.ArgumentParser(description="Show table chunks of a course")
    p.add_argument("course_id", type=int)
    p.add_argument("--source", default="", help="part of the file name")
    p.add_argument("--chars", type=int, default=1500, help="max characters per table (0 = all)")
    p.add_argument("--out", default="", help="write to this file")
    args = p.parse_args()

    # .env first: importing rag.* loads settings, which need it.
    load_env_file()
    from rag.vector_store import DEFAULT_PERSIST_DIR

    client = chromadb.PersistentClient(
        path=DEFAULT_PERSIST_DIR, settings=ChromaSettings(anonymized_telemetry=False)
    )
    collection = client.get_collection(f"course_{args.course_id}")
    found = collection.get(where={"content_type": "table"}, include=["documents", "metadatas"])

    items = sorted(
        zip(found["documents"], found["metadatas"]),
        key=lambda x: (x[1].get("source", ""), x[1].get("page", 0)),
    )
    items = [(d, m) for d, m in items if args.source.lower() in m.get("source", "").lower()]

    out = open(args.out, "w", encoding="utf-8") if args.out else sys.stdout
    try:
        out.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass
    for doc, meta in items:
        text = doc if not args.chars or len(doc) <= args.chars else doc[:args.chars] + "\n[...]"
        out.write(f"\n===== {meta.get('source')} — Seite {meta.get('page')} ({len(doc)} Zeichen)\n")
        out.write(text + "\n")
    out.write(f"\n{len(items)} table chunks\n")
    if args.out:
        out.close()
        print(f"{len(items)} table chunks -> {args.out}")


if __name__ == "__main__":
    main()
    