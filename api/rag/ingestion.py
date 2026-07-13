import os
from dataclasses import dataclass

from .chunker import TextChunker
from .embeddings import EmbeddingModel
from .vector_store import VectorStore


@dataclass
class IngestionResult:
    collection_name: str
    source: str
    chunks_added: int
    success: bool
    error: str = None


class IngestionPipeline:
    """
    End-to-end pipeline for loading documents into the vector store.

    Usage:
        pipeline = IngestionPipeline()
        result = pipeline.ingest_text(
            text="...",
            collection_name="sdg_course_1",
            metadata={"source": "lecture_1", "course": "SDG_basics"}
        )
    """

    def __init__(
        self,
        chunker: TextChunker = None,
        embedding_model: EmbeddingModel = None,
        vector_store: VectorStore = None,
        chunk_size: int = 1000,
        chunk_overlap: int = 150,
    ):
        self.chunker = chunker or TextChunker(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        self.embedding_model = embedding_model or EmbeddingModel()
        self.vector_store = vector_store or VectorStore(
            embedding_model=self.embedding_model
        )

    def ingest_text(
        self,
        text: str,
        collection_name: str,
        metadata: dict = None,
        source: str = "unknown",
    ) -> IngestionResult:
        """
        Ingest raw text into the vector store.

        text: the document content
        collection_name: which ChromaDB collection to store in
        metadata: extra info attached to every chunk (course, lecture, etc.)
        source: human-readable name for logging
        """
        metadata = metadata or {}
        if "source" not in metadata:
            metadata["source"] = source

        try:
            # Step 1: chunk
            chunks = self.chunker.split(text, metadata=metadata)
            if not chunks:
                return IngestionResult(
                    collection_name=collection_name,
                    source=source,
                    chunks_added=0,
                    success=False,
                    error="No chunks produced — text may be too short",
                )

            # Step 2: embed
            embedded = self.embedding_model.embed_chunks(chunks)

            # Step 3: store
            added = self.vector_store.add_embedded_chunks(collection_name, embedded)

            print(f"[ingestion] '{source}' → {added} chunks added to '{collection_name}'")

            return IngestionResult(
                collection_name=collection_name,
                source=source,
                chunks_added=added,
                success=True,
            )

        except Exception as e:
            return IngestionResult(
                collection_name=collection_name,
                source=source,
                chunks_added=0,
                success=False,
                error=str(e),
            )

    def ingest_file(
        self,
        file_path: str,
        collection_name: str,
        metadata: dict = None,
    ) -> IngestionResult:
        """
        Ingest a plain text file (.txt) into the vector store.
        For PDF and .mbz we will add separate parsers later.
        """
        if not os.path.exists(file_path):
            return IngestionResult(
                collection_name=collection_name,
                source=file_path,
                chunks_added=0,
                success=False,
                error=f"File not found: {file_path}",
            )

        filename = os.path.basename(file_path)
        metadata = metadata or {}
        metadata.setdefault("source", filename)
        metadata.setdefault("file_path", file_path)

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                text = f.read()
        except Exception as e:
            return IngestionResult(
                collection_name=collection_name,
                source=filename,
                chunks_added=0,
                success=False,
                error=f"Failed to read file: {e}",
            )

        return self.ingest_text(
            text=text,
            collection_name=collection_name,
            metadata=metadata,
            source=filename,
        )

    def ingest_many(
        self,
        documents: list[dict],
        collection_name: str,
    ) -> list[IngestionResult]:
        """
        Ingest multiple documents at once.

        documents: list of dicts with keys:
            - "text": str
            - "metadata": dict (optional)
            - "source": str (optional)

        Returns list of IngestionResult for each document.
        """
        results = []
        for doc in documents:
            result = self.ingest_text(
                text=doc["text"],
                collection_name=collection_name,
                metadata=doc.get("metadata", {}),
                source=doc.get("source", "unknown"),
            )
            results.append(result)

        total = sum(r.chunks_added for r in results)
        success = sum(1 for r in results if r.success)
        print(f"[ingestion] Done: {success}/{len(documents)} documents, {total} total chunks")

        return results