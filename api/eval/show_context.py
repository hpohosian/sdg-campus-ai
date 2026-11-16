"""
Shows what the retriever finds for one question in one course: every
candidate with its cosine score, keyword (BM25) rank, source, page and
whether it is a table — and which of them reach the model (KEPT).

Run from the api/ folder:

    python -m eval.show_context 12 "Welche PtL-Anlagen haben ... Kapazität?"
    python -m eval.show_context 12 "..." --top 40 --out context.txt

Uses the production Retriever (hybrid search, min_score 0.3, n_results 12).
No LLM is called; the question is searched as it is (no translation).
"""

import argparse
import sys

from eval.run_eval import load_env_file


def main() -> None:
    p = argparse.ArgumentParser(description="Show retrieved chunks for a question")
    p.add_argument("course_id", type=int)
    p.add_argument("question")
    p.add_argument("--n-results", type=int, default=12)
    p.add_argument("--min-score", type=float, default=0.3)
    p.add_argument("--top", type=int, default=30, help="how many candidates to list")
    p.add_argument("--out", default="", help="write to this file")
    args = p.parse_args()

    load_env_file()
    from rag.embeddings import EmbeddingModel
    from rag.retriever import Retriever
    from rag.vector_store import VectorStore

    store = VectorStore(embedding_model=EmbeddingModel())
    retriever = Retriever(vector_store=store, min_score=args.min_score)
    name = f"course_{args.course_id}"

    candidates = retriever._hybrid_search(args.question, {name: None}, args.n_results)
    # What the chatbot really sends: retrieve() = filter + top n + page tables.
    kept = retriever.retrieve(args.question, name, n_results=args.n_results)
    kept_ids = {r["id"] for r in kept}
    attached = [r for r in kept if r.get("attached_to")]

    out = open(args.out, "w", encoding="utf-8") if args.out else sys.stdout
    try:
        out.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

    out.write(f"Question: {args.question}\n")
    out.write(f"{len(candidates)} candidates, {len(kept)} sent to the model "
              f"(min_score {args.min_score}, n_results {args.n_results})\n\n")
    for i, r in enumerate(candidates[: args.top], 1):
        meta = r["metadata"]
        status = "KEPT   " if r["id"] in kept_ids else ("low    " if r["score"] < args.min_score else "cut    ")
        table = " TABLE" if meta.get("content_type") == "table" else ""
        preview = r["text"][:110].replace("\n", " ")
        out.write(
            f"{i:>3}. {status} score={r['score']:.3f}  vec={r.get('vector_rank') or '-':>3}  "
            f"bm25={r.get('keyword_rank') or '-':>3}  {meta.get('source', '?')} S.{meta.get('page', '-')}{table}\n"
            f"       {preview}\n"
        )

    out.write(f"\nTables added because text from their page was found: {len(attached)}\n")
    for r in attached:
        out.write(f"  {r['metadata'].get('source')} S.{r['metadata'].get('page')}  ({len(r['text'])} Zeichen)\n")

    # Where are the table chunks, even if far down?
    tables = [(i, r) for i, r in enumerate(candidates, 1) if r["metadata"].get("content_type") == "table"]
    out.write(f"\nTable chunks among the candidates: {len(tables)}\n")
    for i, r in tables:
        out.write(f"  place {i}: score={r['score']:.3f}  {r['metadata'].get('source')} S.{r['metadata'].get('page')}"
                  f"  {'KEPT' if r['id'] in kept_ids else 'not sent'}\n")
    if args.out:
        out.close()
        print(f"written to {args.out}")


if __name__ == "__main__":
    main()
