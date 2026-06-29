"""
Unit tests for backend/services/generation.py

Covers:
- _build_context(): passage block formatting
- _build_history_block(): conversation history formatting
- generate_answer(): prompt assembly, llama-cpp-python response parsing, error handling
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


# ── rewrite_query ─────────────────────────────────────────────────────────────

class TestRewriteQuery:

    @patch("backend.services.generation._get_llm")
    def test_returns_original_when_no_history(self, mock_get_llm):
        """No history → original question returned, LLM never called."""
        from backend.services.generation import rewrite_query
        result = rewrite_query("What is the revenue?", [])
        assert result == "What is the revenue?"
        mock_get_llm.assert_not_called()

    @patch("backend.services.generation._get_llm")
    def test_returns_rewritten_query_with_history(self, mock_get_llm):
        """With history, LLM is called and its output is returned."""
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_llm.create_chat_completion.return_value = {
            "choices": [{"message": {"content": "What are France revenue figures?"}}]
        }

        from backend.services.generation import rewrite_query
        history = [{"question": "Tell me about France.", "answer": "France is a country in Europe."}]
        result = rewrite_query("What about its revenue?", history)

        assert result == "What are France revenue figures?"
        mock_llm.create_chat_completion.assert_called_once()

    @patch("backend.services.generation._get_llm")
    def test_history_text_included_in_prompt(self, mock_get_llm):
        """The conversation history is included in the messages sent to the LLM."""
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_llm.create_chat_completion.return_value = {
            "choices": [{"message": {"content": "rewritten"}}]
        }

        from backend.services.generation import rewrite_query
        history = [{"question": "Tell me about Germany.", "answer": "Germany info here."}]
        rewrite_query("What about it?", history)

        messages = mock_llm.create_chat_completion.call_args.kwargs["messages"]
        user_content = next(m["content"] for m in messages if m["role"] == "user")
        assert "Tell me about Germany." in user_content
        assert "Germany info here." in user_content

    @patch("backend.services.generation._get_llm")
    def test_falls_back_to_original_on_llm_error(self, mock_get_llm):
        """If the LLM call raises, the original question is returned (graceful degradation)."""
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_llm.create_chat_completion.side_effect = RuntimeError("model error")

        from backend.services.generation import rewrite_query
        history = [{"question": "Q", "answer": "A"}]
        result = rewrite_query("What about it?", history)

        assert result == "What about it?"

    @patch("backend.services.generation._get_llm")
    def test_falls_back_to_original_on_empty_llm_response(self, mock_get_llm):
        """If the LLM returns an empty string, the original question is returned."""
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_llm.create_chat_completion.return_value = {
            "choices": [{"message": {"content": "   "}}]
        }

        from backend.services.generation import rewrite_query
        history = [{"question": "Q", "answer": "A"}]
        result = rewrite_query("What about it?", history)

        assert result == "What about it?"


# ── generate_answer ───────────────────────────────────────────────────────────

class TestGenerateAnswer:
    def _sample_chunks(self):
        return [_make_chunk()]

    def _llm_response(self, payload: dict) -> dict:
        return {"choices": [{"message": {"content": json.dumps(payload)}}]}

    @patch("backend.services.generation._get_llm")
    def test_returns_answer_and_found(self, mock_get_llm):
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_llm.create_chat_completion.return_value = self._llm_response({
            "answer": "The value is 42.",
            "found": True,
            "sources": [],
        })

        from backend.services.generation import generate_answer
        result = generate_answer("What is the value?", self._sample_chunks())

        assert result["found"] is True
        assert result["answer"] == "The value is 42."
        assert result["sources"] == []

    @patch("backend.services.generation._get_llm")
    def test_found_false_when_llm_says_not_found(self, mock_get_llm):
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_llm.create_chat_completion.return_value = self._llm_response({
            "answer": "",
            "found": False,
            "sources": [],
        })

        from backend.services.generation import generate_answer
        result = generate_answer("Unknown question", self._sample_chunks())

        assert result["found"] is False
        assert result["answer"] == ""

    @patch("backend.services.generation._get_llm")
    def test_history_included_in_prompt(self, mock_get_llm):
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_llm.create_chat_completion.return_value = self._llm_response({
            "answer": "Follow-up answer.", "found": True, "sources": [],
        })

        history = [{"question": "What is X?", "answer": "X is Y."}]

        from backend.services.generation import generate_answer
        generate_answer("Tell me more about X.", self._sample_chunks(), history=history)

        call_args = mock_llm.create_chat_completion.call_args
        messages = call_args.kwargs.get("messages") or call_args.args[0]
        user_content = next(m["content"] for m in messages if m["role"] == "user")
        assert "CONVERSATION HISTORY" in user_content
        assert "What is X?" in user_content

    @patch("backend.services.generation._get_llm")
    def test_no_history_prompt_has_no_history_block(self, mock_get_llm):
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_llm.create_chat_completion.return_value = self._llm_response({
            "answer": "Answer.", "found": True, "sources": [],
        })

        from backend.services.generation import generate_answer
        generate_answer("Some question.", self._sample_chunks(), history=None)

        call_args = mock_llm.create_chat_completion.call_args
        messages = call_args.kwargs.get("messages") or call_args.args[0]
        user_content = next(m["content"] for m in messages if m["role"] == "user")
        assert "CONVERSATION HISTORY" not in user_content

    @patch("backend.services.generation._get_llm")
    def test_json_decode_error_raises_runtime_error(self, mock_get_llm):
        # Malformed JSON from LLM is an API failure, not a "not found" answer.
        # It must raise RuntimeError so the caller can return 503.
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_llm.create_chat_completion.return_value = {
            "choices": [{"message": {"content": "not valid json {{{"}}]
        }

        from backend.services.generation import generate_answer
        with pytest.raises(RuntimeError, match="malformed JSON"):
            generate_answer("Question?", self._sample_chunks())

    @patch("backend.services.generation._get_llm")
    def test_llm_exception_raises_runtime_error(self, mock_get_llm):
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_llm.create_chat_completion.side_effect = RuntimeError("model not found")

        from backend.services.generation import generate_answer
        with pytest.raises(RuntimeError, match="LLM error"):
            generate_answer("Question?", self._sample_chunks())
