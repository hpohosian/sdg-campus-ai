import os
import uuid
import chromadb
from chromadb.config import Settings as ChromaSettings

from .embeddings import EmbeddingModel


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
        for text, metadata, distance in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            output.append({
                "text": text,
                "metadata": metadata,
                "distance": distance,
                "score": round(1 - distance, 4),
            })

        # Sort by score descending (most relevant first)
        output.sort(key=lambda x: x["score"], reverse=True)
        return output

    def count(self, collection_name: str) -> int:
        """Return number of chunks in a collection."""
        if not self.collection_exists(collection_name):
            return 0
        return self.get_or_create_collection(collection_name).count()