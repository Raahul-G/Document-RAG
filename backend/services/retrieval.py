"""
Hybrid retrieval pipeline: BM25 keyword + ChromaDB vector → merge → soft rerank.

Flow:
  1. Embed query with nomic-embed-text
  2. Vector search (ChromaDB, top 15)
  3. BM25 keyword search (top 15)
  4. Merge + deduplicate by (doc_id, page, passage_index)
  5. Gate 1 (coverage check) — reject only if retrieval is genuinely empty/weak
  6. Cross-encoder scoring → sigmoid probabilities (no hard threshold, ranking only)
  7. Fallback — if all CE probs < 0.1, bypass reranker and use raw retrieval order
  8. Combined score = 0.5 * vector_sim + 0.3 * bm25_norm + 0.2 * ce_prob
  9. Return 1–MAX_CHUNKS_TO_LLM chunks based on score-ratio cutoff
  Gate 2 (found:false) lives in the LLM — it decides if chunks answer the question.
"""
from __future__ import annotations

import logging
import math

from fastembed.rerank.cross_encoder import TextCrossEncoder

from backend.services import bm25_index, vectorstore
from backend.services.embeddings import embed_query

logger = logging.getLogger(__name__)

# ── Tuning knobs ──────────────────────────────────────────────────────────────
HYBRID_CANDIDATES = 15          # candidates from each source (higher = better recall)
MAX_CHUNKS_TO_LLM = 5           # hard upper limit on chunks passed to LLM
SCORE_RATIO_CUTOFF = 0.5        # drop chunks scoring below 50% of top chunk's score
VECTOR_WEIGHT = 0.5
BM25_WEIGHT = 0.3
CE_WEIGHT = 0.2

# Gate 1 thresholds (retrieval coverage signals, NOT cross-encoder logits)
COVERAGE_VECTOR_MIN = 0.35      # min top-1 vector similarity to pass Gate 1
FALLBACK_CE_PROB_MIN = 0.15     # if max CE prob below this → bypass reranker entirely

_reranker: TextCrossEncoder | None = None
RERANKER_MODEL = "Xenova/ms-marco-MiniLM-L-6-v2"


def _sigmoid(x: float) -> float:
    """Convert a raw cross-encoder logit to a [0, 1] probability."""
    return 1.0 / (1.0 + math.exp(-max(-500.0, min(500.0, x))))


def _get_reranker() -> TextCrossEncoder:
    global _reranker
    if _reranker is None:
        _reranker = TextCrossEncoder(model_name=RERANKER_MODEL)
    return _reranker


def _chunk_key(meta: dict) -> str:
    return f"{meta['doc_id']}_{meta['page_number']}_{meta['passage_index']}"


def retrieve(
    query: str,
    doc_ids: list[int] | None = None,
) -> tuple[list[dict], bool]:
    """
    Run hybrid retrieval with soft reranking.

    Returns:
        (chunks, coverage_ok)
        chunks       — 1–MAX_CHUNKS_TO_LLM chunks sorted by combined score
        coverage_ok  — False only if corpus has no relevant content (Gate 1 fail)
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

    # ── Gate 1: coverage check (retrieval signals only) ───────────────────────
    top_vector_sim = vector_results[0]["score"] if vector_results else 0.0
    bm25_hits = len(bm25_results)

    if not vector_results and not bm25_results:
        logger.info("Gate1 FAIL — no results from either source. query=%r", query)
        return [], False

    if top_vector_sim < COVERAGE_VECTOR_MIN and bm25_hits == 0:
        logger.info(
            "Gate1 FAIL — weak retrieval: top_vector_sim=%.3f bm25_hits=0. query=%r",
            top_vector_sim, query,
        )
        return [], False

    logger.info(
        "Gate1 PASS — top_vector_sim=%.3f bm25_hits=%d. query=%r",
        top_vector_sim, bm25_hits, query,
    )

    # 4. Merge by chunk identity, normalise BM25 scores to [0, 1]
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

    # Initial ordering by hybrid score before cross-encoder
    candidates = sorted(
        merged.values(),
        key=lambda x: VECTOR_WEIGHT * x["vector_score"] + BM25_WEIGHT * x["bm25_score"],
        reverse=True,
    )

    # 5. Cross-encoder → sigmoid probabilities (ranking only, no hard gate)
    reranker = _get_reranker()
    raw_scores = list(reranker.rerank(query=query, documents=[c["text"] for c in candidates]))
    ce_probs = [_sigmoid(s) for s in raw_scores]

    for chunk, ce_prob in zip(candidates, ce_probs):
        chunk["ce_prob"] = ce_prob

    max_ce_prob = max(ce_probs) if ce_probs else 0.0

    # 6. Fallback: reranker confused → trust raw retrieval order, zero out CE contribution
    if max_ce_prob < FALLBACK_CE_PROB_MIN:
        logger.info(
            "Fallback mode — max_ce_prob=%.3f < %.3f, bypassing reranker",
            max_ce_prob, FALLBACK_CE_PROB_MIN,
        )
        for chunk in candidates:
            chunk["ce_prob"] = 0.0

    # 7. Combined score — CE adds soft boost, never used as a hard filter
    for chunk in candidates:
        chunk["final_score"] = (
            VECTOR_WEIGHT * chunk["vector_score"]
            + BM25_WEIGHT * chunk["bm25_score"]
            + CE_WEIGHT * chunk["ce_prob"]
        )

    ranked = sorted(candidates, key=lambda x: x["final_score"], reverse=True)

    # 8. Dynamic selection: include chunks down to 50% of top score, cap at MAX_CHUNKS_TO_LLM
    top_score = ranked[0]["final_score"] if ranked else 0.0
    top: list[dict] = []
    for chunk in ranked:
        if len(top) >= MAX_CHUNKS_TO_LLM:
            break
        if len(top) == 0 or chunk["final_score"] >= top_score * SCORE_RATIO_CUTOFF:
            top.append(chunk)
        else:
            break  # score dropped below ratio — stop here

    logger.info(
        "Retrieval done — candidates=%d returned=%d max_ce_prob=%.3f top_final_score=%.3f",
        len(candidates), len(top),
        max_ce_prob,
        top[0]["final_score"] if top else 0.0,
    )

    return top, True
