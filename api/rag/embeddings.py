import os
from api.settings import settings
os.environ["HF_HOME"] = settings.HF_HOME
os.environ["HF_HUB_DISABLE_XET"] = "1"

from sentence_transformers import SentenceTransformer
from .chunker import Chunk
import numpy as np


# Best model for multilingual content (English + German + others)
# 768-dimensional vectors, good balance of quality and speed
DEFAULT_MODEL = settings.EMBEDDING_MODEL


class EmbeddingModel:
    """
    Wraps sentence-transformers to produce embeddings for RAG pipeline.

    The model is loaded once and reused — loading is expensive (~1-2 sec),
    inference is fast (~ms per chunk).
    """

    def __init__(self, model_name: str = DEFAULT_MODEL):
        print(f"Loading embedding model: {model_name}")
        self.model = SentenceTransformer(model_name)
        self.model_name = model_name
        print("Embedding model loaded.")

    def embed_text(self, text: str) -> list[float]:
        """
        Embed a single string.
        Used for embedding the user's query at search time.
        """
        vector = self.model.encode(text, convert_to_numpy=True)
        return vector.tolist()

    def embed_chunks(self, chunks: list[Chunk]) -> list[dict]:
        """
        Embed a list of Chunk objects.
        Used at ingestion time when loading documents into vector store.

        Returns list of dicts:
        {
            "text": str,
            "embedding": list[float],
            "metadata": dict,
            "chunk_index": int
        }
        """
        if not chunks:
            return []

        texts = [chunk.text for chunk in chunks]

        # Batch encoding is much faster than encoding one by one
        vectors = self.model.encode(
            texts,
            convert_to_numpy=True,
            show_progress_bar=len(chunks) > 10,  # show progress for large batches
            batch_size=32,
        )

        return [
            {
                "text": chunk.text,
                "embedding": vector.tolist(),
                "metadata": chunk.metadata,
                "chunk_index": chunk.chunk_index,
            }
            for chunk, vector in zip(chunks, vectors)
        ]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Embed a list of raw strings.
        Utility method for cases where you don't have Chunk objects.
        """
        if not texts:
            return []

        vectors = self.model.encode(
            texts,
            convert_to_numpy=True,
            show_progress_bar=len(texts) > 10,
            batch_size=32,
        )
        return [v.tolist() for v in vectors]

    @property
    def dimension(self) -> int:
        """Return the dimensionality of the embedding vectors."""
        return self.model.get_embedding_dimension()
    