"""
Unit tests for backend/services/retrieval.py

Covers:
- _sigmoid(): logit → probability conversion
- Coverage Gate 1: empty corpus, weak vector sim with no BM25
- Fallback mode: triggered when max CE prob < threshold
- Combined score formula
- Minimum chunk count enforced
"""
from __future__ import annotations

import math
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from backend.services.retrieval import (
    COVERAGE_VECTOR_MIN,
    FALLBACK_CE_PROB_MIN,
    MIN_CHUNKS_TO_LLM,
    _sigmoid,
)


# ── _sigmoid ──────────────────────────────────────────────────────────────────

class TestSigmoid:
    def test_zero_gives_half(self):
        assert _sigmoid(0.0) == pytest.approx(0.5)

    def test_large_positive_approaches_one(self):
        assert _sigmoid(20.0) > 0.999

    def test_large_negative_approaches_zero(self):
        assert _sigmoid(-20.0) < 0.001

    def test_known_logit(self):
        # sigmoid(1) = e/(1+e) ≈ 0.7311
        assert _sigmoid(1.0) == pytest.approx(1 / (1 + math.exp(-1)), rel=1e-6)

    def test_clamps_extreme_values(self):
        # Should not raise OverflowError for extreme inputs
        assert _sigmoid(-1000.0) >= 0.0
        assert _sigmoid(1000.0) <= 1.0


# ── Coverage Gate 1 ───────────────────────────────────────────────────────────

def _make_chunk(vector_score: float, bm25_score: float = 0.0) -> dict:
    return {
        "text": "sample text",
        "metadata": {"doc_id": 1, "page_number": 1, "passage_index": 1,
                     "doc_name": "test.pdf", "section_title": ""},
        "score": vector_score,
        "vector_score": vector_score,
        "bm25_score": bm25_score,
    }


class TestGate1:
    @patch("backend.services.retrieval.embed_query", return_value=[0.1] * 768)
    @patch("backend.services.retrieval.vectorstore.query_chunks", return_value=[])
    @patch("backend.services.retrieval.bm25_index.search", return_value=[])
    def test_empty_corpus_returns_false(self, _bm25, _vec, _embed):
        from backend.services.retrieval import retrieve
        chunks, ok = retrieve("anything")
        assert ok is False
        assert chunks == []

    @patch("backend.services.retrieval.embed_query", return_value=[0.1] * 768)
    @patch("backend.services.retrieval.vectorstore.query_chunks")
    @patch("backend.services.retrieval.bm25_index.search", return_value=[])
    def test_weak_vector_no_bm25_returns_false(self, _bm25, mock_vec, _embed):
        # top vector similarity below COVERAGE_VECTOR_MIN, no BM25 hits
        weak_chunk = _make_chunk(vector_score=COVERAGE_VECTOR_MIN - 0.05)
        mock_vec.return_value = [weak_chunk]

        from backend.services.retrieval import retrieve
        chunks, ok = retrieve("obscure query")
        assert ok is False
        assert chunks == []

    @patch("backend.services.retrieval.embed_query", return_value=[0.1] * 768)
    @patch("backend.services.retrieval.vectorstore.query_chunks")
    @patch("backend.services.retrieval.bm25_index.search", return_value=[])
    @patch("backend.services.retrieval.CrossEncoder")
    def test_strong_vector_passes_gate(self, mock_ce_cls, _bm25, mock_vec, _embed):
        strong_chunk = _make_chunk(vector_score=0.75)
        mock_vec.return_value = [strong_chunk]

        mock_ce = MagicMock()
        mock_ce.predict.return_value = np.array([2.0])  # positive logit → CE prob ~0.88
        mock_ce_cls.return_value = mock_ce

        with patch("backend.services.retrieval._reranker", mock_ce):
            from backend.services.retrieval import retrieve
            chunks, ok = retrieve("relevant query")

        assert ok is True
        assert len(chunks) >= 1


# ── Fallback mode ─────────────────────────────────────────────────────────────

class TestFallbackMode:
    def _make_candidates(self, n: int = 3, vector_score: float = 0.6) -> list[dict]:
        return [
            {
                "text": f"chunk {i}",
                "metadata": {"doc_id": 1, "page_number": 1, "passage_index": i,
                             "doc_name": "test.pdf", "section_title": ""},
                "score": vector_score,
                "vector_score": vector_score,
                "bm25_score": 0.0,
            }
            for i in range(n)
        ]

    @patch("backend.services.retrieval.embed_query", return_value=[0.1] * 768)
    @patch("backend.services.retrieval.vectorstore.query_chunks")
    @patch("backend.services.retrieval.bm25_index.search", return_value=[])
    def test_fallback_triggered_when_ce_probs_low(self, _bm25, mock_vec, _embed):
        chunks = self._make_candidates(3, vector_score=0.6)
        mock_vec.return_value = chunks

        mock_ce = MagicMock()
        # very low logit → sigmoid ≈ 0.000 (below FALLBACK_CE_PROB_MIN)
        mock_ce.predict.return_value = np.array([-20.0, -20.0, -20.0])

        with patch("backend.services.retrieval._reranker", mock_ce):
            from backend.services.retrieval import retrieve
            result_chunks, ok = retrieve("vague query")

        assert ok is True
        # In fallback mode, ce_prob is zeroed — final_score = 0.5*vec + 0.3*bm25
        for c in result_chunks:
            assert c["ce_prob"] == 0.0


# ── Min chunks enforced ───────────────────────────────────────────────────────

class TestMinChunks:
    @patch("backend.services.retrieval.embed_query", return_value=[0.1] * 768)
    @patch("backend.services.retrieval.vectorstore.query_chunks")
    @patch("backend.services.retrieval.bm25_index.search", return_value=[])
    def test_returns_up_to_min_chunks(self, _bm25, mock_vec, _embed):
        # Provide more candidates than MIN_CHUNKS_TO_LLM
        candidates = [
            {
                "text": f"text {i}",
                "metadata": {"doc_id": 1, "page_number": 1, "passage_index": i,
                             "doc_name": "test.pdf", "section_title": ""},
                "score": 0.8,
                "vector_score": 0.8,
                "bm25_score": 0.0,
            }
            for i in range(MIN_CHUNKS_TO_LLM + 4)
        ]
        mock_vec.return_value = candidates

        mock_ce = MagicMock()
        mock_ce.predict.return_value = np.array([5.0] * len(candidates))

        with patch("backend.services.retrieval._reranker", mock_ce):
            from backend.services.retrieval import retrieve
            result_chunks, ok = retrieve("good query")

        assert ok is True
        assert len(result_chunks) == MIN_CHUNKS_TO_LLM
