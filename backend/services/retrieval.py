"""
Hybrid retrieval pipeline: BM25 keyword + ChromaDB vector → merge → cross-encoder rerank.

Flow:
  1. Embed query with nomic-embed-text
  2. Vector search (ChromaDB, top 10)
  3. Keyword search (BM25, top 10)
  4. Merge + deduplicate by (doc_id, page, passage_index)
  5. Cross-encoder rerank → top 3
  6. Threshold gate: if best score < threshold → "not found"
"""
from __future__ import annotations

from sentence_transformers import CrossEncoder

from backend.services import bm25_index, vectorstore
from backend.services.embeddings import embed_query

# Tuning knobs
HYBRID_CANDIDATES = 10      # candidates from each source
VECTOR_WEIGHT = 0.6
BM25_WEIGHT = 0.4
RERANK_TOP_N = 3
NOT_FOUND_THRESHOLD = -8.0  # cross-encoder score below this → "not found"

_reranker: CrossEncoder | None = None
RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


def _get_reranker() -> CrossEncoder:
    global _reranker
    if _reranker is None:
        _reranker = CrossEncoder(RERANKER_MODEL)
    return _reranker


def _chunk_key(meta: dict) -> str:
    return f"{meta['doc_id']}_{meta['page_number']}_{meta['passage_index']}"


def retrieve(
    query: str,
    n_results: int = RERANK_TOP_N,
    doc_ids: list[int] | None = None,
) -> tuple[list[dict], float]:
    """
    Run hybrid retrieval + reranking.

    Returns:
        (chunks, top_score)
        chunks: list of {text, metadata, score} dicts, sorted by relevance
        top_score: best cross-encoder score (used for threshold gate)
    """
    # 1. Embed query
    query_vec = embed_query(query)

    # 2. Vector search
    vector_results = vectorstore.query_chunks(
        query_vec, n_results=HYBRID_CANDIDATES, doc_ids=doc_ids
    )

    # 3. BM25 keyword search
    bm25_results = bm25_index.search(
        query, n_results=HYBRID_CANDIDATES, doc_ids=doc_ids
    )

    # 4. Merge by chunk identity key, normalise scores
    merged: dict[str, dict] = {}

    for chunk in vector_results:
        key = _chunk_key(chunk["metadata"])
        merged[key] = {**chunk, "vector_score": chunk["score"], "bm25_score": 0.0}

    if bm25_results:
        max_bm25 = max(r["score"] for r in bm25_results) or 1.0
        for chunk in bm25_results:
            key = _chunk_key(chunk["metadata"])
            norm = chunk["score"] / max_bm25
            if key in merged:
                merged[key]["bm25_score"] = norm
            else:
                merged[key] = {**chunk, "vector_score": 0.0, "bm25_score": norm}

    # Combined score for initial ordering before rerank
    candidates = sorted(
        merged.values(),
        key=lambda x: VECTOR_WEIGHT * x["vector_score"] + BM25_WEIGHT * x["bm25_score"],
        reverse=True,
    )

    if not candidates:
        return [], -999.0

    # 5. Cross-encoder rerank
    reranker = _get_reranker()
    pairs = [[query, c["text"]] for c in candidates]
    scores = reranker.predict(pairs).tolist()

    for chunk, score in zip(candidates, scores):
        chunk["rerank_score"] = score

    reranked = sorted(candidates, key=lambda x: x["rerank_score"], reverse=True)
    top = reranked[:n_results]
    top_score = top[0]["rerank_score"] if top else -999.0

    return top, top_score
