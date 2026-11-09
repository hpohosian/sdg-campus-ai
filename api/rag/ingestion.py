import bisect
import re
import os
from dataclasses import dataclass

from .chunker import TextChunker
from .embeddings import EmbeddingModel
from .vector_store import VectorStore

_WS = re.compile(r"\s+")


def _norm(text: str) -> str:
    return _WS.sub(" ", text or "").strip()


def assign_pages(chunks, page_texts: list[str]) -> None:
    """
    Sets chunk.metadata["page"] (1-based) for chunks of a PDF.

    The chunker does not keep character offsets, so each chunk is found
    again in the whole text: whitespace is normalised on both sides (the
    chunker re-joins paragraphs), and a piece from the MIDDLE of the chunk
    is searched — the start may be overlap from the previous chunk, i.e.
    from the previous page. A chunk spanning two pages gets the page where
    its middle is. Not found (should not happen) -> no "page" key.
    """
    starts, parts, pos = [], [], 0
    for page in page_texts:
        norm = _norm(page)
        starts.append(pos)
        parts.append(norm)
        pos += len(norm) + 1                    # +1 for the joining space
    full = " ".join(parts)

    search_from = 0
    for chunk in chunks:
        text = _norm(chunk.text)
        if not text:
            continue
        mid = len(text) // 2
        probes = [text[max(0, mid - 30): mid + 30], text[-60:], text[:60]]
        found = -1
        for probe in probes:
            if len(probe) < 10:
                continue
            found = full.find(probe, max(0, search_from - 2000))
            if found < 0:
                found = full.find(probe)
            if found >= 0:
                break
        if found < 0:
            continue
        search_from = found
        page = bisect.bisect_right(starts, found)   # 1-based page number
        chunk.metadata = {**chunk.metadata, "page": page}


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
        page_texts: list[str] | None = None,
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
            if page_texts:
                assign_pages(chunks, page_texts)
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
                page_texts=doc.get("page_texts"),
            )
            results.append(result)

        total = sum(r.chunks_added for r in results)
        success = sum(1 for r in results if r.success)
        print(f"[ingestion] Done: {success}/{len(documents)} documents, {total} total chunks")

        return results
    