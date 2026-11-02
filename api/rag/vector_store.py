import os
import uuid
import chromadb
import numpy as np
from chromadb.config import Settings as ChromaSettings

from .embeddings import EmbeddingModel
from .bm25 import BM25Index


# Where ChromaDB stores its data on disk
DEFAULT_PERSIST_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "chromadb"
)


class VectorStore:
    """
    Wrapper around ChromaDB for storing and searching document embeddings.

    Each 'collection' is like a table — one collection per course or document set.
    Collections are created automatically if they don't exist.
    """

    def __init__(
        self,
        persist_dir: str = DEFAULT_PERSIST_DIR,
        embedding_model: EmbeddingModel = None,
    ):
        os.makedirs(persist_dir, exist_ok=True)

        self.client = chromadb.PersistentClient(
            path=persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self.embedding_model = embedding_model or EmbeddingModel()
        # collection name -> (chunk count when built, ids, texts, metadatas, BM25Index)
        self._bm25_cache: dict[str, tuple] = {}

    # ─────────────────────────────────────────
    # Collection management
    # ─────────────────────────────────────────

    def get_or_create_collection(self, collection_name: str):
        """Get existing collection or create a new one."""
        return self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},  # use cosine similarity
        )

    def list_collections(self) -> list[str]:
        """List all existing collections."""
        return [col.name for col in self.client.list_collections()]

    def delete_collection(self, collection_name: str) -> None:
        """Delete a collection and all its data."""
        self.client.delete_collection(collection_name)

    def collection_exists(self, collection_name: str) -> bool:
        """Check if a collection exists."""
        return collection_name in self.list_collections()

    # ─────────────────────────────────────────
    # Adding documents
    # ─────────────────────────────────────────

    def add_embedded_chunks(
        self,
        collection_name: str,
        embedded_chunks: list[dict],
    ) -> int:
        """
        Add pre-embedded chunks to a collection.

        embedded_chunks: output of EmbeddingModel.embed_chunks()
        Each item: {"text", "embedding", "metadata", "chunk_index"}

        Returns number of chunks added.
        """
        if not embedded_chunks:
            return 0

        collection = self.get_or_create_collection(collection_name)

        ids = [str(uuid.uuid4()) for _ in embedded_chunks]
        embeddings = [item["embedding"] for item in embedded_chunks]
        documents = [item["text"] for item in embedded_chunks]
        metadatas = [
            {**item["metadata"], "chunk_index": item["chunk_index"]}
            for item in embedded_chunks
        ]

        collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )

        return len(embedded_chunks)

    # ─────────────────────────────────────────
    # Searching
    # ─────────────────────────────────────────

    def search(
        self,
        collection_name: str,
        query: str,
        n_results: int = 5,
        where: dict = None,
        query_embedding: list[float] = None,
    ) -> list[dict]:
        """
        Search for most relevant chunks by query string.

        query: natural language question from user
        n_results: how many chunks to return
        where: optional metadata filter e.g. {"course": "SDG_basics"}

        Returns list of dicts:
        {
            "text": str,
            "metadata": dict,
            "distance": float,  # lower = more similar
            "score": float,     # higher = more similar (1 - distance)
        }
        """
        if not self.collection_exists(collection_name):
            return []

        collection = self.get_or_create_collection(collection_name)

        # Check collection is not empty
        if collection.count() == 0:
            return []

        if query_embedding is None:
            query_embedding = self.embedding_model.embed_text(query)

        kwargs = {
            "query_embeddings": [query_embedding],
            "n_results": min(n_results, collection.count()),
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where

        results = collection.query(**kwargs)

        # Flatten ChromaDB's nested result format into clean list
        output = []
        for chunk_id, text, metadata, distance in zip(
            results["ids"][0],
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            output.append({
                "id": chunk_id,
                "text": text,
                "metadata": metadata,
                "distance": distance,
                "score": round(1 - distance, 4),
            })

        # Sort by score descending (most relevant first)
        output.sort(key=lambda x: x["score"], reverse=True)
        return output

    # ─────────────────────────────────────────
    # Keyword search (BM25) — used by Retriever for hybrid search
    # ─────────────────────────────────────────

    def _bm25(self, collection_name: str):
        """
        BM25 index of a collection, built from the stored chunks on first use
        and rebuilt automatically when the chunk count changes (reindex).
        Building takes well under a second for a course.
        """
        collection = self.get_or_create_collection(collection_name)
        count = collection.count()
        cached = self._bm25_cache.get(collection_name)
        if cached and cached[0] == count:
            return cached
        got = collection.get(include=["documents", "metadatas"])
        ids, texts, metas = got["ids"], got["documents"] or [], got["metadatas"] or []
        entry = (count, ids, texts, metas, BM25Index(texts))
        self._bm25_cache[collection_name] = entry
        return entry

    def keyword_search(self, collection_name: str, query: str, n_results: int = 30) -> list[dict]:
        """Top chunks by BM25: [{"id", "text", "metadata", "bm25"}], best first."""
        if not self.collection_exists(collection_name):
            return []
        _, ids, texts, metas, index = self._bm25(collection_name)
        return [
            {"id": ids[i], "text": texts[i], "metadata": metas[i] or {}, "bm25": score}
            for i, score in index.search(query, n_results)
        ]

    def similarity_for_ids(
        self, collection_name: str, query_embedding: list[float], ids: list[str]
    ) -> dict[str, float]:
        """Cosine similarity (same scale as search()["score"]) for given chunk ids."""
        if not ids:
            return {}
        got = self.get_or_create_collection(collection_name).get(ids=ids, include=["embeddings"])
        q = np.asarray(query_embedding, dtype=float)
        q_norm = np.linalg.norm(q) or 1.0
        out = {}
        for chunk_id, emb in zip(got["ids"], got["embeddings"]):
            v = np.asarray(emb, dtype=float)
            out[chunk_id] = round(float(q @ v / (q_norm * (np.linalg.norm(v) or 1.0))), 4)
        return out

    def count(self, collection_name: str) -> int:
        """Return number of chunks in a collection."""
        if not self.collection_exists(collection_name):
            return 0
        return self.get_or_create_collection(collection_name).count()
    