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
    ) -> str:
        """
        Retrieve chunks and format them as a context string for LLM prompt.

        Returns formatted string like:
        [Source: lecture_1]
        <text of chunk>

        [Source: lecture_2]
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
            source = chunk["metadata"].get("source", "unknown")
            parts.append(f"[Source: {source}]\n{chunk['text']}")

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
    ) -> list[dict]:
        """
        Search across multiple course collections (only the ones the user
        is enrolled in) and return the globally top-N most relevant chunks.

        Each result gets metadata["course_id"] attached so the LLM/prompt
        can mention which course a piece of context came from.
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

        filtered = [r for r in all_results if r["score"] >= threshold]
        filtered.sort(key=lambda x: x["score"], reverse=True)

        return filtered[:n]

    def retrieve_as_context_global(
        self,
        query: str,
        course_ids: list[int],
        n_results: int = None,
        min_score: float = None,
        where: dict = None,
    ) -> str:
        """
        Same as retrieve_as_context(), but searches across all of the
        user's enrolled courses instead of a single collection.
        """
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
            source = chunk["metadata"].get("source", "unknown")
            course_id = chunk["metadata"].get("course_id", "?")
            parts.append(f"[Course {course_id} — Source: {source}]\n{chunk['text']}")

        return "\n\n".join(parts)
    