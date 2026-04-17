"""
Unit tests for streaming generation (stream_answer).

Covers:
- Token events yielded for normal answers
- NOT_FOUND sentinel suppressed and found=False returned
- done event always emitted as final event
- Partial sentinel buffering (sentinel split across chunks)
- RuntimeError raised on Gemini ClientError
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


def _raw_chunk(text: str) -> MagicMock:
    """Simulate a Gemini streaming chunk."""
    c = MagicMock()
    c.text = text
    return c


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

    @patch("backend.services.generation._get_client")
    def test_normal_answer_yields_tokens_and_done(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.models.generate_content_stream.return_value = iter([
            _raw_chunk("The answer "),
            _raw_chunk("is 42."),
        ])

        from backend.services.generation import stream_answer
        tokens, found = _collect(stream_answer("What is it?", [_make_chunk()]))

        assert found is True
        assert "".join(tokens).strip() != ""

    @patch("backend.services.generation._get_client")
    def test_not_found_sentinel_suppressed(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.models.generate_content_stream.return_value = iter([
            _raw_chunk(_NOT_FOUND_SENTINEL),
        ])

        from backend.services.generation import stream_answer
        tokens, found = _collect(stream_answer("Unknown?", [_make_chunk()]))

        assert found is False
        assert all(_NOT_FOUND_SENTINEL not in t for t in tokens)

    @patch("backend.services.generation._get_client")
    def test_done_always_last_event(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.models.generate_content_stream.return_value = iter([
            _raw_chunk("Some answer text here."),
        ])

        from backend.services.generation import stream_answer
        events = list(stream_answer("Question?", [_make_chunk()]))

        assert events[-1]["type"] == "done"

    @patch("backend.services.generation._get_client")
    def test_sentinel_split_across_chunks(self, mock_get_client):
        """NOT_FOUND split as 'NOT_' and 'FOUND' should still be detected."""
        sentinel = _NOT_FOUND_SENTINEL
        mid = len(sentinel) // 2
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.models.generate_content_stream.return_value = iter([
            _raw_chunk(sentinel[:mid]),
            _raw_chunk(sentinel[mid:]),
        ])

        from backend.services.generation import stream_answer
        tokens, found = _collect(stream_answer("Unknown?", [_make_chunk()]))

        assert found is False

    @patch("backend.services.generation._get_client")
    def test_history_passed_to_prompt(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.models.generate_content_stream.return_value = iter([
            _raw_chunk("Follow-up answer."),
        ])
        history = [{"question": "First Q", "answer": "First A"}]

        from backend.services.generation import stream_answer
        list(stream_answer("Follow-up Q", [_make_chunk()], history=history))

        call_args = mock_client.models.generate_content_stream.call_args
        prompt = call_args.kwargs.get("contents") or call_args.args[1]
        assert "CONVERSATION HISTORY" in prompt
        assert "First Q" in prompt

    @patch("backend.services.generation._get_client")
    def test_client_error_raises_runtime_error(self, mock_get_client):
        from google.genai import errors as genai_errors

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        err = genai_errors.ClientError("503", {"error": {"code": 503, "message": "unavailable"}})
        mock_client.models.generate_content_stream.side_effect = err

        from backend.services.generation import stream_answer
        with pytest.raises(RuntimeError, match="LLM unavailable"):
            list(stream_answer("Question?", [_make_chunk()]))

    @patch("backend.services.generation._get_client")
    def test_empty_stream_returns_not_found(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.models.generate_content_stream.return_value = iter([])

        from backend.services.generation import stream_answer
        tokens, found = _collect(stream_answer("Question?", [_make_chunk()]))

        assert found is False
        assert tokens == []
