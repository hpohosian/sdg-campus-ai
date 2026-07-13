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

    def __init__(
        self,
        vector_store: VectorStore,
        min_score: float = 0.3,
        n_results: int = 5,
    ):
        self.vector_store = vector_store
        self.min_score = min_score
        self.n_results = n_results

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

        results = self.vector_store.search(
            collection_name=collection_name,
            query=query,
            n_results=n,
            where=where,
        )

        # Filter by minimum relevance score
        filtered = [r for r in results if r["score"] >= threshold]

        return filtered

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

        all_results = []
        for course_id in course_ids:
            collection_name = f"course_{course_id}"
            results = self.vector_store.search(
                collection_name=collection_name,
                query=query,
                n_results=n,
                where=where,
            )
            for r in results:
                r["metadata"] = {**r["metadata"], "course_id": course_id}
            all_results.extend(results)

        all_results.sort(key=lambda x: x["score"], reverse=True)

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
    