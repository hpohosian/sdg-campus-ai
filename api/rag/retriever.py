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
    