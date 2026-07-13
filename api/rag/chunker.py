import re
from dataclasses import dataclass, field


@dataclass
class Chunk:
    text: str
    metadata: dict = field(default_factory=dict)
    chunk_index: int = 0


# Matches sentence-ending punctuation followed by whitespace or end of string.
# Handles ".", "!", "?" and keeps common abbreviations from being treated
# as hard failures (not perfect, but good enough — worst case we just
# fall back to a slightly-off split point, never a random mid-word cut).
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


class TextChunker:
    """
    Splits text into overlapping chunks for the RAG pipeline.

    Unlike a naive fixed-character splitter, this chunker respects text
    structure:
      1. The text is first split into paragraphs (on blank lines).
      2. Paragraphs are greedily packed into chunks up to ~chunk_size.
      3. A paragraph larger than chunk_size is split into sentences,
         which are then packed the same way.
      4. Only a single sentence longer than chunk_size on its own gets a
         hard character-based cut — this should be rare.

    This guarantees that a chunk boundary (almost) never lands in the
    middle of a sentence, which is what was causing specific facts
    (a date, a named list) to sometimes get truncated right at the
    chunk edge.

    chunk_size: target size of each chunk in characters (soft target,
                a chunk may run a bit over to avoid splitting a unit)
    chunk_overlap: how many characters of the *previous* chunk's tail
                   (aligned to whole sentences) get prepended to the next
                   chunk, to preserve context across the boundary
    min_chunk_size: discard chunks smaller than this
    """

    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 150,
        min_chunk_size: int = 100,
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size

    # ─────────────────────────────────────────
    # Public API — same signature as before
    # ─────────────────────────────────────────

    def split(self, text: str, metadata: dict = None) -> list[Chunk]:
        """Split text into chunks, preferring paragraph/sentence boundaries."""
        text = text.strip()
        if not text:
            return []
        metadata = metadata or {}

        units = self._split_into_units(text)
        raw_chunks = self._pack_units(units)

        chunks = []
        index = 0
        for chunk_text in raw_chunks:
            chunk_text = chunk_text.strip()
            if len(chunk_text) >= self.min_chunk_size:
                chunks.append(Chunk(
                    text=chunk_text,
                    metadata=metadata.copy(),
                    chunk_index=index,
                ))
                index += 1

        return chunks

    # ─────────────────────────────────────────
    # Step 1: break the document into "units" that must never be
    # split apart mid-way (paragraphs, or sentences for oversized
    # paragraphs, or hard slices for a single oversized sentence)
    # ─────────────────────────────────────────

    def _split_into_units(self, text: str) -> list[str]:
        paragraphs = re.split(r"\n\s*\n", text)
        units = []

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            if len(para) <= self.chunk_size:
                units.append(para)
                continue

            # Paragraph itself is too big — split into sentences
            for sentence in self._split_into_sentences(para):
                units.append(sentence)

        return units

    def _split_into_sentences(self, paragraph: str) -> list[str]:
        sentences = _SENTENCE_SPLIT_RE.split(paragraph)
        result = []
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            if len(sentence) <= self.chunk_size:
                result.append(sentence)
            else:
                # Single sentence longer than chunk_size on its own.
                # Last resort: hard character slice. This should be rare.
                for i in range(0, len(sentence), self.chunk_size):
                    result.append(sentence[i:i + self.chunk_size])
        return result

    # ─────────────────────────────────────────
    # Step 2: greedily pack units into chunks up to ~chunk_size,
    # carrying sentence-aligned overlap forward between chunks
    # ─────────────────────────────────────────

    def _pack_units(self, units: list[str]) -> list[str]:
        if not units:
            return []

        chunks = []
        current_units: list[str] = []
        current_len = 0

        for unit in units:
            unit_len = len(unit) + 1  # +1 for the joining space/newline

            if current_units and current_len + unit_len > self.chunk_size:
                chunks.append(" ".join(current_units))

                # Build overlap tail from the end of the chunk we just closed,
                # keeping whole units so we never re-cut a sentence.
                overlap_units = self._take_overlap_tail(current_units)
                current_units = overlap_units[:]
                current_len = sum(len(u) + 1 for u in current_units)

            current_units.append(unit)
            current_len += unit_len

        if current_units:
            chunks.append(" ".join(current_units))

        return chunks

    def _take_overlap_tail(self, units: list[str]) -> list[str]:
        """Return the trailing whole units of `units` totalling ~chunk_overlap chars."""
        if self.chunk_overlap <= 0:
            return []

        tail = []
        total = 0
        for unit in reversed(units):
            if total >= self.chunk_overlap:
                break
            tail.insert(0, unit)
            total += len(unit) + 1

        return tail
    