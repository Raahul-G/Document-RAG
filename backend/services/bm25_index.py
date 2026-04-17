"""
In-memory BM25 keyword search index.
Built from all chunks at server startup, rebuilt when new documents are ingested.
"""
from __future__ import annotations

from rank_bm25 import BM25Okapi

_index: BM25Okapi | None = None
_corpus: list[dict] = []  # parallel to index rows: [{text, metadata}, ...]


def _tokenize(text: str) -> list[str]:
    return text.lower().split()


def build_index(chunks: list[dict]) -> None:
    """Build BM25 index from a list of {text, metadata} dicts."""
    global _index, _corpus
    _corpus = chunks
    if not chunks:
        _index = None
        return
    tokenized = [_tokenize(c["text"]) for c in chunks]
    _index = BM25Okapi(tokenized)


def search(query: str, n_results: int = 10, doc_ids: list[int] | None = None) -> list[dict]:
    """
    Keyword search using BM25. Returns list of {text, metadata, score} dicts.
    Optionally filter to specific document IDs.
    """
    if _index is None or not _corpus:
        return []

    tokens = _tokenize(query)
    scores = _index.get_scores(tokens)

    ranked = sorted(
        enumerate(scores), key=lambda x: x[1], reverse=True
    )

    results = []
    for idx, score in ranked:
        if score <= 0:
            continue
        chunk = _corpus[idx]
        if doc_ids and chunk["metadata"]["doc_id"] not in doc_ids:
            continue
        results.append({**chunk, "score": float(score)})
        if len(results) >= n_results:
            break

    return results
