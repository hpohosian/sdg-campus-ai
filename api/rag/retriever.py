from .vector_store import VectorStore
from .embeddings import EmbeddingModel


class Retriever:
    """
    Retrieves relevant chunks from vector store for a given query.

    This sits between the vector store and the LLM:
    - Filters out low-relevance results
    - Formats context for the prompt
    - Optionally filters by course/source
    """

    # Reciprocal Rank Fusion constant (standard value from the RRF paper).
    _RRF_K = 60

    def __init__(
        self,
        vector_store: VectorStore,
        min_score: float = 0.3,
        n_results: int = 5,
        hybrid: bool = True,
        candidates: int = 40,
        keyword_reserved: int = 3,
    ):
        """
        hybrid: combine vector search with keyword search (BM25). See
            _hybrid_search. False = the old vector-only behaviour.
        candidates: how many chunks EACH method contributes before fusion.
        keyword_reserved: the best N keyword hits always get a place in the
            result (if they pass min_score), see _hybrid_search.
        """
        self.vector_store = vector_store
        self.min_score = min_score
        self.n_results = n_results
        self.hybrid = hybrid
        self.candidates = candidates
        self.keyword_reserved = keyword_reserved

    def _hybrid_search(self, query: str, collections: dict[str, int | None], n: int, where: dict = None) -> list[dict]:
        """
        Candidates from several collections, best first.

        collections: {collection_name: course_id or None}. The course_id is
            attached to each chunk's metadata (global mode needs it).

        Vector search finds chunks with the same MEANING, keyword search
        (BM25) chunks with the same WORDS (names, numbers, compound terms,
        table rows — what vector search misses). The two rankings are merged
        with Reciprocal Rank Fusion: score = sum of 1/(60 + rank) over both
        lists, so a chunk ranked high by either method comes up.

        RRF alone does not lift a chunk that ONLY keyword search finds:
        chunks ranked moderately in both lists beat it (1/61 < 1/70 + 1/75).
        That is exactly the "exact term" case hybrid search is for, so the
        best `keyword_reserved` keyword hits are moved to the front.

        Every chunk keeps its cosine "score" (also chunks found only by BM25
        get one), and min_score still applies to it in retrieve() — keyword
        search can promote a relevant chunk, but cannot drag in a chunk
        whose meaning is unrelated to the question.
        """
        store = self.vector_store
        pool = max(n, self.candidates) if self.hybrid else n
        query_embedding = store.embedding_model.embed_text(query)

        vector_hits, keyword_hits = [], []
        for name, course_id in collections.items():
            for r in store.search(collection_name=name, query=query, n_results=pool,
                                  where=where, query_embedding=query_embedding):
                r["collection"] = name
                if course_id is not None:
                    r["metadata"] = {**r["metadata"], "course_id": course_id}
                vector_hits.append(r)
            # Keyword search ignores `where` filters, so only without them.
            if self.hybrid and not where:
                for r in store.keyword_search(name, query, n_results=pool):
                    r["collection"] = name
                    if course_id is not None:
                        r["metadata"] = {**r["metadata"], "course_id": course_id}
                    keyword_hits.append(r)

        vector_hits.sort(key=lambda r: r["score"], reverse=True)
        if not keyword_hits:
            return vector_hits[:n] if not self.hybrid else vector_hits

        keyword_hits.sort(key=lambda r: r["bm25"], reverse=True)
        keyword_hits = keyword_hits[:pool]

        merged: dict[str, dict] = {}
        for rank, r in enumerate(vector_hits, 1):
            merged[r["id"]] = {**r, "rrf": 1 / (self._RRF_K + rank), "vector_rank": rank}
        missing_scores: dict[str, list[str]] = {}
        for rank, r in enumerate(keyword_hits, 1):
            entry = merged.get(r["id"])
            if entry is None:
                entry = merged[r["id"]] = {**r, "score": None, "rrf": 0.0, "vector_rank": None}
                missing_scores.setdefault(r["collection"], []).append(r["id"])
            entry["rrf"] += 1 / (self._RRF_K + rank)
            entry["keyword_rank"] = rank

        for name, ids in missing_scores.items():
            scores = store.similarity_for_ids(name, query_embedding, ids)
            for chunk_id in ids:
                merged[chunk_id]["score"] = scores.get(chunk_id, 0.0)

        fused = sorted(merged.values(), key=lambda r: r["rrf"], reverse=True)
        reserved_ids = {r["id"] for r in keyword_hits[: self.keyword_reserved]}
        reserved = [r for r in fused if r["id"] in reserved_ids]
        rest = [r for r in fused if r["id"] not in reserved_ids]
        # Reserved hits first, then the rest by fused rank. Overall order
        # inside the context does not matter much to the LLM; what matters
        # is that these chunks are not cut off by the top-n limit.
        return reserved + rest

    @staticmethod
    def _format_source_label(chunk_metadata: dict) -> str:
        """
        Builds the citation label for a chunk's source file.

        If the chunk's metadata carries a "file_url" (set by pdf_loader.py
        at ingestion time — a direct Moodle pluginfile.php link), returns
        a ready-made markdown link, e.g. "[Butin2010.pdf](http://.../...)".
        Otherwise falls back to the plain filename, same as before this
        file-linking feature existed — older/already-indexed documents
        without a stored file_url still degrade gracefully instead of
        breaking.
        """
        source = chunk_metadata.get("source", "unknown")
        file_url = chunk_metadata.get("file_url")
        if file_url:
            return f"[{source}]({file_url})"
        return source

    def retrieve(
        self,
        query: str,
        collection_name: str,
        n_results: int = None,
        min_score: float = None,
        where: dict = None,
    ) -> list[dict]:
        """
        Retrieve relevant chunks for a query.

        Returns filtered and sorted list of chunks:
        [{"text", "metadata", "score", "distance"}, ...]
        """
        n = n_results or self.n_results
        threshold = min_score if min_score is not None else self.min_score

        if not self.vector_store.collection_exists(collection_name):
            return []
        results = self._hybrid_search(query, {collection_name: None}, n, where)

        # Filter by minimum relevance score, then keep the best n
        filtered = [r for r in results if r["score"] >= threshold]

        return filtered[:n]

    def retrieve_as_context(
        self,
        query: str,
        collection_name: str,
        n_results: int = None,
        min_score: float = None,
        where: dict = None,
        course_link: str = None,
    ) -> str:
        """
        Retrieve chunks and format them as a context string for LLM prompt.

        course_link: an already-built markdown link for the course, e.g.
            "[PtX-Lab-Challenge](http://127.0.0.1/course/view.php?id=12)".
            Build this with course_links.format_course_link() — the
            retriever itself never constructs URLs, it only places a
            ready string into the tag so the LLM has nothing to invent.

        Returns formatted string like:
        [Course: [PtX-Lab-Challenge](...) — Source: lecture_1.pdf]
        <text of chunk>
        """
        chunks = self.retrieve(
            query=query,
            collection_name=collection_name,
            n_results=n_results,
            min_score=min_score,
            where=where,
        )

        if not chunks:
            return ""

        parts = []
        for chunk in chunks:
            source_label = self._format_source_label(chunk["metadata"])
            if course_link:
                parts.append(f"[Course: {course_link} — Source: {source_label}]\n{chunk['text']}")
            else:
                parts.append(f"[Source: {source_label}]\n{chunk['text']}")

        return "\n\n".join(parts)

    def has_relevant_context(
        self,
        query: str,
        collection_name: str,
        min_score: float = None,
    ) -> bool:
        """
        Check if there is any relevant context for a query.
        Useful to decide whether to use RAG or fall back to plain LLM.
        """
        results = self.retrieve(
            query=query,
            collection_name=collection_name,
            n_results=1,
            min_score=min_score,
        )
        return len(results) > 0
    
    def retrieve_global(
        self,
        query: str,
        course_ids: list[int],
        n_results: int = None,
        min_score: float = None,
        where: dict = None,
        debug: bool = False,
    ) -> list[dict]:
        """
        Search across multiple course collections (only the ones the user
        is enrolled in) and return the globally top-N most relevant chunks.

        Each result gets metadata["course_id"] attached so the LLM/prompt
        can mention which course a piece of context came from.

        debug: if True, prints EVERY candidate (before the min_score filter
               and before the n_results cutoff) with its score and source,
               sorted best-first. Use this to see whether a chunk you expect
               to be retrieved (a) doesn't exist in the collection at all,
               (b) exists but scores below min_score, or (c) exists and
               scores fine but gets pushed out of the top-N by other chunks.
               Leave this off in production — it's verbose and only meant
               for local diagnosis.
        """
        n = n_results or self.n_results
        threshold = min_score if min_score is not None else self.min_score

        collections = {
            f"course_{cid}": cid for cid in course_ids
            if self.vector_store.collection_exists(f"course_{cid}")
        }
        if not collections:
            return []
        all_results = self._hybrid_search(query, collections, n, where)

        if debug:
            print(f"\n[retriever debug] query={query!r}  threshold={threshold}  n_results={n}")
            for r in all_results:
                source = r["metadata"].get("source", "unknown")
                course_id = r["metadata"].get("course_id", "?")
                kept = "KEPT" if r["score"] >= threshold else "DROPPED (below min_score)"
                preview = r["text"][:80].replace("\n", " ")
                print(f"  score={r['score']:.4f}  course={course_id}  source={source}  [{kept}]  {preview}...")
            print()

        filtered = [r for r in all_results if r["score"] >= threshold]

        return filtered[:n]

    def retrieve_as_context_global(
        self,
        query: str,
        course_ids: list[int],
        n_results: int = None,
        min_score: float = None,
        where: dict = None,
        course_links: dict[int, str] = None,
    ) -> str:
        """
        Same as retrieve_as_context(), but searches across all of the
        user's enrolled courses instead of a single collection.

        course_links: {course_id: markdown_link}, built via
            course_links.build_course_links(). If a course_id isn't in
            the dict (lookup failed), falls back to a plain "Course {id}"
            label so the citation still degrades gracefully.
        """
        course_links = course_links or {}

        chunks = self.retrieve_global(
            query=query,
            course_ids=course_ids,
            n_results=n_results,
            min_score=min_score,
            where=where,
            debug=True
        )

        if not chunks:
            return ""

        parts = []
        for chunk in chunks:
            source_label = self._format_source_label(chunk["metadata"])
            course_id = chunk["metadata"].get("course_id", "?")
            course_label = course_links.get(course_id, f"Course {course_id}")
            parts.append(f"[Course: {course_label} — Source: {source_label}]\n{chunk['text']}")

        return "\n\n".join(parts)
    
    
    def retrieve_global_smart(
        self,
        last_message: str,
        combined_query: str,
        course_ids: list[int],
        n_results: int = None,
        min_score: float = None,
        where: dict = None,
    ) -> list[dict]:
        """
        Two-tier retrieval for follow-up-aware search without letting an
        unrelated multi-message query dilute a genuine topic switch.

        1. Try searching with ONLY the latest user message. If that alone
           clears min_score, trust it — the student just asked about a
           new/different topic, and blending in the previous question
           would only hurt.
        2. Only if that comes back empty, fall back to the combined
           (last N messages) query — this is the case a short follow-up
           like "can you explain more?" needs the earlier message's
           context to mean anything in embedding space.
        """
        if last_message and last_message.strip():
            narrow = self.retrieve_global(
                query=last_message,
                course_ids=course_ids,
                n_results=n_results,
                min_score=min_score,
                where=where,
            )
            if narrow:
                return narrow

        if combined_query and combined_query != last_message:
            return self.retrieve_global(
                query=combined_query,
                course_ids=course_ids,
                n_results=n_results,
                min_score=min_score,
                where=where,
            )

        return []

    def retrieve_as_context_global_smart(
        self,
        last_message: str,
        combined_query: str,
        course_ids: list[int],
        n_results: int = None,
        min_score: float = None,
        where: dict = None,
        course_links: dict[int, str] = None,
    ) -> str:
        course_links = course_links or {}

        chunks = self.retrieve_global_smart(
            last_message=last_message,
            combined_query=combined_query,
            course_ids=course_ids,
            n_results=n_results,
            min_score=min_score,
            where=where,
        )

        if not chunks:
            return ""

        parts = []
        for chunk in chunks:
            source_label = self._format_source_label(chunk["metadata"])
            course_id = chunk["metadata"].get("course_id", "?")
            course_label = course_links.get(course_id, f"Course {course_id}")
            parts.append(f"[Course: {course_label} — Source: {source_label}]\n{chunk['text']}")

        return "\n\n".join(parts)
    
    
    def retrieve_as_context_smart(
        self,
        last_message: str,
        combined_query: str,
        collection_name: str,
        n_results: int = None,
        min_score: float = None,
        where: dict = None,
        course_link: str = None,
    ) -> str:
        """Same two-tier logic as retrieve_as_context_global_smart, for the
        single-course search path."""
        chunks = []
        if last_message and last_message.strip():
            chunks = self.retrieve(
                query=last_message,
                collection_name=collection_name,
                n_results=n_results,
                min_score=min_score,
                where=where,
            )

        if not chunks and combined_query and combined_query != last_message:
            chunks = self.retrieve(
                query=combined_query,
                collection_name=collection_name,
                n_results=n_results,
                min_score=min_score,
                where=where,
            )

        if not chunks:
            return ""

        parts = []
        for chunk in chunks:
            source_label = self._format_source_label(chunk["metadata"])
            if course_link:
                parts.append(f"[Course: {course_link} — Source: {source_label}]\n{chunk['text']}")
            else:
                parts.append(f"[Source: {source_label}]\n{chunk['text']}")

        return "\n\n".join(parts)
    