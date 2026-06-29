"""
Unit tests for streaming generation (stream_answer).

Covers:
- Token events yielded for normal answers
- NOT_FOUND sentinel suppressed and found=False returned
- done event always emitted as final event
- Partial sentinel buffering (sentinel split across chunks)
- RuntimeError raised on LLM error
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from backend.services.generation import _NOT_FOUND_SENTINEL


def _make_chunk(text="Sample text."):
    return {
        "text": text,
        "metadata": {
            "doc_name": "test.pdf", "page_number": 1,
            "passage_index": 1, "section_title": "",
        },
    }


def _stream_chunk(content: str) -> dict:
    """Simulate a llama-cpp-python streaming chunk with content."""
    return {"choices": [{"delta": {"content": content}, "finish_reason": None}]}


def _stream_stop() -> dict:
    """Simulate a llama-cpp-python streaming stop chunk."""
    return {"choices": [{"delta": {}, "finish_reason": "stop"}]}


def _collect(gen) -> tuple[list[str], bool]:
    """Run generator, return (token_texts, found)."""
    tokens, found = [], False
    for event in gen:
        if event["type"] == "token":
            tokens.append(event["text"])
        elif event["type"] == "done":
            found = event["found"]
    return tokens, found


class TestStreamAnswer:

    @patch("backend.services.generation._get_llm")
    def test_normal_answer_yields_tokens_and_done(self, mock_get_llm):
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_llm.create_chat_completion.return_value = iter([
            _stream_chunk("The answer "),
            _stream_chunk("is 42."),
            _stream_stop(),
        ])

        from backend.services.generation import stream_answer
        tokens, found = _collect(stream_answer("What is it?", [_make_chunk()]))

        assert found is True
        assert "".join(tokens).strip() != ""

    @patch("backend.services.generation._get_llm")
    def test_not_found_sentinel_suppressed(self, mock_get_llm):
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_llm.create_chat_completion.return_value = iter([
            _stream_chunk(_NOT_FOUND_SENTINEL),
            _stream_stop(),
        ])

        from backend.services.generation import stream_answer
        tokens, found = _collect(stream_answer("Unknown?", [_make_chunk()]))

        assert found is False
        assert all(_NOT_FOUND_SENTINEL not in t for t in tokens)

    @patch("backend.services.generation._get_llm")
    def test_done_always_last_event(self, mock_get_llm):
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_llm.create_chat_completion.return_value = iter([
            _stream_chunk("Some answer text here."),
            _stream_stop(),
        ])

        from backend.services.generation import stream_answer
        events = list(stream_answer("Question?", [_make_chunk()]))

        assert events[-1]["type"] == "done"

    @patch("backend.services.generation._get_llm")
    def test_sentinel_split_across_chunks(self, mock_get_llm):
        """NOT_FOUND split as 'NOT_' and 'FOUND' should still be detected."""
        sentinel = _NOT_FOUND_SENTINEL
        mid = len(sentinel) // 2
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_llm.create_chat_completion.return_value = iter([
            _stream_chunk(sentinel[:mid]),
            _stream_chunk(sentinel[mid:]),
            _stream_stop(),
        ])

        from backend.services.generation import stream_answer
        tokens, found = _collect(stream_answer("Unknown?", [_make_chunk()]))

        assert found is False

    @patch("backend.services.generation._get_llm")
    def test_history_passed_to_prompt(self, mock_get_llm):
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_llm.create_chat_completion.return_value = iter([
            _stream_chunk("Follow-up answer."),
            _stream_stop(),
        ])
        history = [{"question": "First Q", "answer": "First A"}]

        from backend.services.generation import stream_answer
        list(stream_answer("Follow-up Q", [_make_chunk()], history=history))

        call_args = mock_llm.create_chat_completion.call_args
        messages = call_args.kwargs.get("messages") or call_args.args[0]
        user_content = next(m["content"] for m in messages if m["role"] == "user")
        assert "CONVERSATION HISTORY" in user_content
        assert "First Q" in user_content

    @patch("backend.services.generation._get_llm")
    def test_llm_error_raises_runtime_error(self, mock_get_llm):
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_llm.create_chat_completion.side_effect = RuntimeError("llama error")

        from backend.services.generation import stream_answer
        with pytest.raises(RuntimeError, match="LLM error"):
            list(stream_answer("Question?", [_make_chunk()]))

    @patch("backend.services.generation._get_llm")
    def test_empty_stream_returns_not_found(self, mock_get_llm):
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_llm.create_chat_completion.return_value = iter([])

        from backend.services.generation import stream_answer
        tokens, found = _collect(stream_answer("Question?", [_make_chunk()]))

        assert found is False
        assert tokens == []
