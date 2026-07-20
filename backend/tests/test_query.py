"""
Tests for backend/routers/query.py

Covers:
- Non-streaming source text restoration: LLM-paraphrased text in `sources`
  is replaced with the original retrieved chunk text so the snippet highlighter
  always searches for verbatim PDF content.
- Source text is NOT replaced when the (doc_name, page, passage_index) key
  does not match any retrieved chunk (e.g. a hallucinated citation).
- Multiple sources — only matching keys are restored.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


# ── helpers ───────────────────────────────────────────────name──────────────────

def _make_chunk(
    doc_name: str = "report.pdf",
    page: int = 1,
    passage_index: int = 1,
    text: str = "Original verbatim chunk text from the PDF.",
    section: str = "Introduction",
) -> dict:
    return {
        "text": text,
        "metadata": {
            "doc_name": doc_name,
            "page_number": page,
            "passage_index": passage_index,
            "section_title": section,
            "doc_id": 1,
        },
    }


def _generation_result(answer: str, sources: list[dict], found: bool = True) -> dict:
    return {"answer": answer, "found": found, "sources": sources}


# ── Source text restoration ───────────────────────────────────────────────────

class TestSourceTextRestoration:
    """
    The non-streaming endpoint must replace LLM-paraphrased source text
    with the original retrieved chunk text before returning to the client.
    This prevents the snippet highlighter from searching for text that doesn't
    exist verbatim in the PDF.
    """

    @patch("backend.routers.query.retrieval.retrieve")
    @patch("backend.routers.query.generation.generate_answer")
    def test_llm_paraphrase_replaced_with_original_text(
        self, mock_gen, mock_retrieve
    ):
        original_text = "Original verbatim chunk text from the PDF."
        paraphrased_text = "LLM rewrote this as a paraphrase of the passage."

        chunk = _make_chunk(
            doc_name="report.pdf", page=2, passage_index=3, text=original_text
        )
        mock_retrieve.return_value = ([chunk], True)
        mock_gen.return_value = _generation_result(
            answer="Some answer.",
            sources=[
                {
                    "doc_name": "report.pdf",
                    "page": 2,
                    "passage_index": 3,
                    "section_title": "Introduction",
                    "text": paraphrased_text,  # LLM paraphrased this
                }
            ],
        )

        resp = client.post(
            "/api/query",
            json={"question": "What does the report say?", "session_id": None},
        )
        assert resp.status_code == 200
        data = resp.json()

        assert data["found"] is True
        assert len(data["sources"]) == 1
        assert data["sources"][0]["text"] == original_text, (
            "LLM paraphrase should be replaced with original chunk text"
        )

    @patch("backend.routers.query.retrieval.retrieve")
    @patch("backend.routers.query.generation.generate_answer")
    def test_unmatched_source_text_preserved(self, mock_gen, mock_retrieve):
        """A source whose key is not in retrieved chunks is left unchanged."""
        original_text = "Real chunk text."
        hallucinated_text = "Hallucinated citation text."

        chunk = _make_chunk(doc_name="report.pdf", page=1, passage_index=1, text=original_text)
        mock_retrieve.return_value = ([chunk], True)
        mock_gen.return_value = _generation_result(
            answer="Answer.",
            sources=[
                {
                    "doc_name": "other.pdf",   # different doc — no match in retrieved
                    "page": 99,
                    "passage_index": 5,
                    "section_title": "Ghost",
                    "text": hallucinated_text,
                }
            ],
        )

        resp = client.post(
            "/api/query",
            json={"question": "Some question?", "session_id": None},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["sources"][0]["text"] == hallucinated_text, (
            "Unmatched source text should be preserved as-is"
        )

    @patch("backend.routers.query.retrieval.retrieve")
    @patch("backend.routers.query.generation.generate_answer")
    def test_multiple_sources_only_matching_keys_restored(self, mock_gen, mock_retrieve):
        """With two sources, only the one whose key matches a retrieved chunk is restored."""
        real_text = "Verbatim text from chunk A."
        paraphrase_a = "Paraphrased version of chunk A."
        paraphrase_b = "Paraphrased chunk B — no matching retrieved chunk."

        chunk_a = _make_chunk(
            doc_name="doc.pdf", page=1, passage_index=1, text=real_text
        )
        # chunk_b is not in retrieved results
        mock_retrieve.return_value = ([chunk_a], True)
        mock_gen.return_value = _generation_result(
            answer="Answer using both.",
            sources=[
                {
                    "doc_name": "doc.pdf",
                    "page": 1,
                    "passage_index": 1,
                    "section_title": "S",
                    "text": paraphrase_a,
                },
                {
                    "doc_name": "doc.pdf",
                    "page": 2,
                    "passage_index": 2,
                    "section_title": "S2",
                    "text": paraphrase_b,
                },
            ],
        )

        resp = client.post(
            "/api/query",
            json={"question": "Question?", "session_id": None},
        )
        assert resp.status_code == 200
        sources = resp.json()["sources"]

        # Source A: key matched → restored to original
        src_a = next(s for s in sources if s.get("passage_index") == 1)
        assert src_a["text"] == real_text

        # Source B: key not matched → unchanged paraphrase
        src_b = next(s for s in sources if s.get("passage_index") == 2)
        assert src_b["text"] == paraphrase_b

    @patch("backend.routers.query.retrieval.retrieve")
    @patch("backend.routers.query.generation.generate_answer")
    def test_restoration_key_uses_doc_name_page_passage_index(self, mock_gen, mock_retrieve):
        """Verify the restoration lookup uses all three key fields — a partial match fails."""
        text = "Exact chunk text."
        chunk = _make_chunk(doc_name="a.pdf", page=1, passage_index=1, text=text)
        mock_retrieve.return_value = ([chunk], True)

        # Source has wrong page — should NOT be restored
        mock_gen.return_value = _generation_result(
            answer="A.",
            sources=[
                {
                    "doc_name": "a.pdf",
                    "page": 99,           # wrong page
                    "passage_index": 1,
                    "section_title": "X",
                    "text": "wrong paraphrase",
                }
            ],
        )

        resp = client.post("/api/query", json={"question": "Q?", "session_id": None})
        assert resp.status_code == 200
        assert resp.json()["sources"][0]["text"] == "wrong paraphrase"

    @patch("backend.routers.query.retrieval.retrieve")
    def test_gate1_miss_returns_found_false_no_sources(self, mock_retrieve):
        """Coverage gate 1 miss returns found=False with empty sources (no generation called)."""
        mock_retrieve.return_value = ([], False)

        resp = client.post("/api/query", json={"question": "Irrelevant?", "session_id": None})
        assert resp.status_code == 200
        data = resp.json()
        assert data["found"] is False
        assert data["sources"] == []


# ── Query rewriting integration ───────────────────────────────────────────────

class TestQueryRewriting:
    """
    Verify that the rewritten query is used for retrieval and that the original
    question is still passed to generate_answer (rewriting is retrieval-only).
    """

    @patch("backend.routers.query.generation.rewrite_query")
    @patch("backend.routers.query.retrieval.retrieve")
    @patch("backend.routers.query.generation.generate_answer")
    def test_retrieve_called_with_rewritten_query(
        self, mock_gen, mock_retrieve, mock_rewrite
    ):
        """retrieve() must receive the rewritten query, not the raw question."""
        mock_rewrite.return_value = "France revenue figures"
        mock_retrieve.return_value = ([_make_chunk()], True)
        mock_gen.return_value = _generation_result("Answer.", [])

        resp = client.post(
            "/api/query",
            json={"question": "What about its revenue?", "session_id": None},
        )
        assert resp.status_code == 200

        call_query = (
            mock_retrieve.call_args.kwargs.get("query")
            or mock_retrieve.call_args.args[0]
        )
        assert call_query == "France revenue figures"

    @patch("backend.routers.query.generation.rewrite_query")
    @patch("backend.routers.query.retrieval.retrieve")
    @patch("backend.routers.query.generation.generate_answer")
    def test_generate_answer_uses_original_question(
        self, mock_gen, mock_retrieve, mock_rewrite
    ):
        """generate_answer() must always receive the original question, not the rewritten one."""
        mock_rewrite.return_value = "France revenue figures"
        mock_retrieve.return_value = ([_make_chunk()], True)
        mock_gen.return_value = _generation_result("Answer.", [])

        client.post(
            "/api/query",
            json={"question": "What about its revenue?", "session_id": None},
        )

        original_question = mock_gen.call_args.args[0]
        assert original_question == "What about its revenue?"

    @patch("backend.routers.query.generation.rewrite_query")
    @patch("backend.routers.query.retrieval.retrieve")
    @patch("backend.routers.query.generation.generate_answer")
    def test_rewrite_called_before_retrieve(
        self, mock_gen, mock_retrieve, mock_rewrite
    ):
        """rewrite_query must be called before retrieve on every request."""
        call_order = []
        mock_rewrite.side_effect = lambda q, h: (call_order.append("rewrite"), q)[1]
        mock_retrieve.side_effect = lambda **kw: (call_order.append("retrieve"), ([_make_chunk()], True))[1]
        mock_gen.return_value = _generation_result("Answer.", [])

        client.post("/api/query", json={"question": "Q?", "session_id": None})

        assert call_order.index("rewrite") < call_order.index("retrieve")
