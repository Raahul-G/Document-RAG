"""
Unit tests for backend/services/generation.py

Covers:
- _build_context(): passage block formatting
- _build_history_block(): conversation history formatting
- generate_answer(): prompt assembly, Gemini response parsing, error handling
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from backend.services.generation import _build_context, _build_history_block


# ── _build_context ────────────────────────────────────────────────────────────

def _make_chunk(doc_name="report.pdf", page=1, passage_index=2, text="Some content.", section="Intro"):
    return {
        "text": text,
        "metadata": {
            "doc_name": doc_name,
            "page_number": page,
            "passage_index": passage_index,
            "section_title": section,
        },
    }


class TestBuildContext:
    def test_contains_passage_header(self):
        ctx = _build_context([_make_chunk()])
        assert "DOCUMENT PASSAGES" in ctx
        assert "[Passage 1]" in ctx

    def test_contains_doc_metadata(self):
        ctx = _build_context([_make_chunk(doc_name="doc.pdf", page=3, passage_index=7)])
        assert "doc.pdf" in ctx
        assert "Page: 3" in ctx
        assert "Passage: 7" in ctx

    def test_contains_chunk_text(self):
        ctx = _build_context([_make_chunk(text="The answer is 42.")])
        assert "The answer is 42." in ctx

    def test_multiple_chunks_numbered(self):
        chunks = [_make_chunk(text=f"Chunk {i}") for i in range(3)]
        ctx = _build_context(chunks)
        assert "[Passage 1]" in ctx
        assert "[Passage 2]" in ctx
        assert "[Passage 3]" in ctx

    def test_missing_section_title_shows_na(self):
        chunk = _make_chunk()
        chunk["metadata"]["section_title"] = ""
        ctx = _build_context([chunk])
        assert "N/A" in ctx

    def test_empty_chunks_returns_header_only(self):
        ctx = _build_context([])
        assert "DOCUMENT PASSAGES" in ctx


# ── _build_history_block ──────────────────────────────────────────────────────

class TestBuildHistoryBlock:
    def test_contains_header(self):
        block = _build_history_block([{"question": "Q1", "answer": "A1"}])
        assert "CONVERSATION HISTORY" in block

    def test_single_turn(self):
        block = _build_history_block([{"question": "What is X?", "answer": "X is Y."}])
        assert "What is X?" in block
        assert "X is Y." in block
        assert "Turn 1" in block

    def test_multiple_turns_ordered(self):
        history = [
            {"question": "First Q", "answer": "First A"},
            {"question": "Second Q", "answer": "Second A"},
        ]
        block = _build_history_block(history)
        assert "Turn 1" in block
        assert "Turn 2" in block
        assert block.index("First Q") < block.index("Second Q")

    def test_empty_history_returns_header(self):
        block = _build_history_block([])
        assert "CONVERSATION HISTORY" in block


# ── generate_answer ───────────────────────────────────────────────────────────

class TestGenerateAnswer:
    def _mock_response(self, payload: dict) -> MagicMock:
        response = MagicMock()
        response.text = json.dumps(payload)
        return response

    def _sample_chunks(self):
        return [_make_chunk()]

    @patch("backend.services.generation._get_client")
    def test_returns_answer_and_found(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.models.generate_content.return_value = self._mock_response({
            "answer": "The value is 42.",
            "found": True,
            "sources": [],
        })

        from backend.services.generation import generate_answer
        result = generate_answer("What is the value?", self._sample_chunks())

        assert result["found"] is True
        assert result["answer"] == "The value is 42."
        assert result["sources"] == []

    @patch("backend.services.generation._get_client")
    def test_found_false_when_gemini_says_not_found(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.models.generate_content.return_value = self._mock_response({
            "answer": "",
            "found": False,
            "sources": [],
        })

        from backend.services.generation import generate_answer
        result = generate_answer("Unknown question", self._sample_chunks())

        assert result["found"] is False
        assert result["answer"] == ""

    @patch("backend.services.generation._get_client")
    def test_history_included_in_prompt(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.models.generate_content.return_value = self._mock_response({
            "answer": "Follow-up answer.", "found": True, "sources": [],
        })

        history = [{"question": "What is X?", "answer": "X is Y."}]

        from backend.services.generation import generate_answer
        generate_answer("Tell me more about X.", self._sample_chunks(), history=history)

        call_args = mock_client.models.generate_content.call_args
        prompt = call_args.kwargs.get("contents") or call_args.args[1]
        assert "CONVERSATION HISTORY" in prompt
        assert "What is X?" in prompt

    @patch("backend.services.generation._get_client")
    def test_no_history_prompt_has_no_history_block(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.models.generate_content.return_value = self._mock_response({
            "answer": "Answer.", "found": True, "sources": [],
        })

        from backend.services.generation import generate_answer
        generate_answer("Some question.", self._sample_chunks(), history=None)

        call_args = mock_client.models.generate_content.call_args
        prompt = call_args.kwargs.get("contents") or call_args.args[1]
        assert "CONVERSATION HISTORY" not in prompt

    @patch("backend.services.generation._get_client")
    def test_json_decode_error_raises_runtime_error(self, mock_get_client):
        # Malformed JSON from Gemini is an API failure, not a "not found" answer.
        # It must raise RuntimeError so the caller can return 503, not silently
        # show "I could not find an answer" to the user.
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        bad_response = MagicMock()
        bad_response.text = "not valid json {{{"
        mock_client.models.generate_content.return_value = bad_response

        from backend.services.generation import generate_answer
        with pytest.raises(RuntimeError, match="malformed JSON"):
            generate_answer("Question?", self._sample_chunks())

    @patch("backend.services.generation._get_client")
    def test_client_error_raises_runtime_error(self, mock_get_client):
        from google.genai import errors as genai_errors

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        # ClientError requires (message, response_json) per the SDK
        err = genai_errors.ClientError("429 quota", {"error": {"code": 429, "message": "quota"}})
        mock_client.models.generate_content.side_effect = err

        from backend.services.generation import generate_answer
        with pytest.raises(RuntimeError, match="LLM unavailable"):
            generate_answer("Question?", self._sample_chunks())
