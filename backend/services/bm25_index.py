"""
In-memory BM25 keyword search index.
Built from all chunks at server startup, rebuilt when new documents are ingested.
Persisted to disk via pickle to avoid slow rebuild on container restart.
"""
from __future__ import annotations

import os
import pickle
import re

from rank_bm25 import BM25Okapi

_index: BM25Okapi | None = None
_corpus: list[dict] = []  # parallel to index rows: [{text, metadata}, ...]

BM25_PKL_PATH = os.getenv("BM25_PKL_PATH", "data/bm25.pkl")


def _tokenize(text: str) -> list[str]:
    return re.sub(r"[^\w\s]", " ", text).lower().split()


def build_index(chunks: list[dict]) -> None:
    """Build BM25 index from a list of {text, metadata} dicts and persist to disk."""
    global _index, _corpus
    _corpus = chunks
    if not chunks:
        _index = None
        return
    tokenized = [_tokenize(c["text"]) for c in chunks]
    _index = BM25Okapi(tokenized)
    _save_index()


def load_index() -> bool:
    """
    Try to load BM25 index from disk.
    Returns True if loaded successfully, False if not found or invalid.
    """
    global _index, _corpus
    pkl_path = BM25_PKL_PATH
    if not os.path.exists(pkl_path):
        return False
    try:
        with open(pkl_path, "rb") as f:
            data = pickle.load(f)
        if not isinstance(data, dict) or "index" not in data or "corpus" not in data:
            return False
        _index = data["index"]
        _corpus = data["corpus"]
        return True
    except Exception:
        return False


def _save_index() -> None:
    """Persist the current index to disk."""
    if _index is None:
        return
    pkl_path = BM25_PKL_PATH
    try:
        with open(pkl_path, "wb") as f:
            pickle.dump({"index": _index, "corpus": _corpus}, f)
    except Exception as e:
        print(f"Warning: failed to save BM25 index to {pkl_path}: {e}")


def invalidate_pickle() -> None:
    """Remove the on-disk pickle (called by migration guard on dimension mismatch)."""
    pkl_path = BM25_PKL_PATH
    if os.path.exists(pkl_path):
        try:
            os.remove(pkl_path)
        except Exception:
            pass


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
