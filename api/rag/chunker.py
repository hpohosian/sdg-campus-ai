from dataclasses import dataclass, field


@dataclass
class Chunk:
    text: str
    metadata: dict = field(default_factory=dict)
    chunk_index: int = 0


class TextChunker:
    """
    Splits text into overlapping chunks for RAG pipeline.
    
    chunk_size: target size of each chunk in characters
    chunk_overlap: how many characters overlap between chunks
                   (helps preserve context at boundaries)
    min_chunk_size: discard chunks smaller than this
    """

    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 500,
        min_chunk_size: int = 100,
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size

    def split(self, text: str, metadata: dict = {}) -> list[Chunk]:
        """Split text into chunks with overlap."""
        text = text.strip()
        if not text:
            return []

        chunks = []
        start = 0
        index = 0

        while start < len(text):
            end = start + self.chunk_size

            # Try to break at a sentence boundary (. ! ?)
            # so chunks don't cut mid-sentence
            if end < len(text):
                boundary = self._find_sentence_boundary(text, end)
                if boundary:
                    end = boundary

            chunk_text = text[start:end].strip()

            if len(chunk_text) >= self.min_chunk_size:
                chunks.append(Chunk(
                    text=chunk_text,
                    metadata=metadata.copy(),
                    chunk_index=index,
                ))
                index += 1

            # Move start forward, but keep overlap
            next_start = end - self.chunk_overlap
            if next_start <= start:
                next_start = start + self.chunk_size - self.chunk_overlap
            start = next_start

        return chunks

    def _find_sentence_boundary(self, text: str, pos: int) -> int | None:
        search_window = 200
        search_start = max(0, pos - search_window)
        segment = text[search_start:pos]
        
        for i in range(len(segment) - 1, -1, -1):
            if segment[i] in ".!?":
                # next_char = segment[i + 1] if i + 1 < len(segment) else "END"
                if i + 1 < len(segment) and segment[i + 1] in " \n":
                    return search_start + i + 2

        return None
    