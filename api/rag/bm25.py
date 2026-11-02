"""
Keyword search (Okapi BM25) over the chunks of one collection.

Why: the embedding model matches MEANING well, but misses exact terms —
names ("Uphues"), compound words ("Investitionsentscheid"), rows of a
table ("Green Fuels Lausitz … 200.000 t/a"). The quality test showed
answer chunks that vector search ranks below place 60 although the
question contains those exact words. BM25 finds them; the Retriever then
merges both rankings (hybrid search, see retriever.py).

No external dependency: a few dozen lines, the index is built in memory
from the chunks already stored in ChromaDB.
"""

import math
import re
import unicodedata
from collections import Counter

_TOKEN = re.compile(r"\w+", re.UNICODE)


def tokenize(text: str) -> list[str]:
    """
    Lowercase words, umlauts folded (ä -> a, ß -> ss), 1-letter tokens dropped.
    Numbers are kept on purpose ("2021", "159") — they are often exactly
    what a student asks about. "200.000" and "200,000" both become "200000".
    """
    text = (text or "").lower().replace("ß", "ss")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"(?<=\d)[.,](?=\d{3}\b)", "", text)
    return [t for t in _TOKEN.findall(text) if len(t) > 1]


class BM25Index:
    def __init__(self, texts: list[str], k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.doc_freqs: list[Counter] = []
        self.doc_lens: list[int] = []
        df: Counter = Counter()

        for text in texts:
            tokens = tokenize(text)
            freqs = Counter(tokens)
            self.doc_freqs.append(freqs)
            self.doc_lens.append(len(tokens))
            df.update(freqs.keys())

        n = len(texts)
        self.avg_len = (sum(self.doc_lens) / n) if n else 0.0
        # BM25+ style idf, never negative (very common words just weigh ~0).
        self.idf = {term: math.log(1 + (n - f + 0.5) / (f + 0.5)) for term, f in df.items()}

    def search(self, query: str, k: int) -> list[tuple[int, float]]:
        """Top-k (document index, score), best first. Documents scoring 0 are skipped."""
        terms = [t for t in set(tokenize(query)) if t in self.idf]
        if not terms or not self.doc_freqs:
            return []

        scores = []
        for i, freqs in enumerate(self.doc_freqs):
            score = 0.0
            length_norm = self.k1 * (1 - self.b + self.b * self.doc_lens[i] / (self.avg_len or 1))
            for t in terms:
                f = freqs.get(t)
                if f:
                    score += self.idf[t] * f * (self.k1 + 1) / (f + length_norm)
            if score > 0:
                scores.append((i, score))

        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:k]
    