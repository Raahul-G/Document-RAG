"""
Answer generation using Gemini via google-genai SDK.

Rules enforced via system prompt:
  - Answer ONLY from provided passages (no external knowledge)
  - Return structured JSON: {answer, found, sources[]}
  - If answer not in passages → found: false, empty answer
"""
from __future__ import annotations

import json
import logging
import time

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from backend.config import settings

logger = logging.getLogger(__name__)

_client: genai.Client | None = None
GEMINI_MODEL = "gemini-2.5-flash"

_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 1.0  # seconds; doubles each attempt (1s, 2s, 4s)


def _is_retryable(e: Exception) -> bool:
    """Return True for transient 503 / overload errors worth retrying."""
    return isinstance(e, genai_errors.ClientError) and "503" in str(e)

# ── Non-streaming prompt (structured JSON) ────────────────────────────────────
SYSTEM_PROMPT = """You are a precise document analysis assistant.

Your ONLY job is to answer questions using the document passages provided to you.

STRICT RULES:
1. Answer ONLY using information found in the provided passages.
2. Do NOT use any external knowledge, training data, or assumptions.
3. You MAY use the conversation history to understand follow-up questions and resolve pronouns
   (e.g. "it", "that", "the second one"), but your answer must still be grounded in the passages.
4. If the answer is NOT found in the passages, set "found" to false and "answer" to an empty string.
5. Always cite the exact passage(s) you used in "sources".
6. Return ONLY valid JSON — no extra text, no markdown fences, no explanation outside the JSON.

Response schema (return exactly this structure):
{
  "answer": "Your answer here, or empty string if not found",
  "found": true or false,
  "sources": [
    {
      "doc_name": "filename",
      "page": 1,
      "passage_index": 1,
      "section_title": "Section name or empty string",
      "text": "The exact passage text used"
    }
  ]
}"""


# ── Streaming prompt (plain text answer) ─────────────────────────────────────
STREAM_SYSTEM_PROMPT = """You are a precise document analysis assistant.

Answer questions using ONLY the document passages provided. No external knowledge.
You MAY use conversation history to understand follow-up questions, but answer from passages only.

OUTPUT RULES — follow exactly:
- Write your answer in plain text. No JSON, no markdown, no bullet points unless natural.
- If the answer is NOT in the passages, reply with ONLY the word: NOT_FOUND
- Do not explain why you cannot answer. Just: NOT_FOUND"""


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


def _build_context(chunks: list[dict]) -> str:
    """Format retrieved chunks into a numbered passage block."""
    lines = ["DOCUMENT PASSAGES:\n"]
    for i, chunk in enumerate(chunks, 1):
        meta = chunk["metadata"]
        lines.append(
            f"[Passage {i}]\n"
            f"Document: {meta['doc_name']}\n"
            f"Page: {meta['page_number']} | Passage: {meta['passage_index']}\n"
            f"Section: {meta.get('section_title') or 'N/A'}\n"
            f"---\n{chunk['text']}\n"
        )
    return "\n".join(lines)


def _build_history_block(history: list[dict]) -> str:
    """Format prior Q&A turns into a conversation history block."""
    lines = ["CONVERSATION HISTORY (for context only — do not answer from this):\n"]
    for i, turn in enumerate(history, 1):
        lines.append(f"Turn {i}:")
        lines.append(f"  User: {turn['question']}")
        lines.append(f"  Assistant: {turn['answer']}\n")
    return "\n".join(lines)


def generate_answer(
    question: str,
    chunks: list[dict],
    history: list[dict] | None = None,
) -> dict:
    """
    Call Gemini with the question + retrieved passages + optional conversation history.
    Returns parsed {answer, found, sources} dict.

    history: list of {question, answer} dicts ordered oldest → newest (max HISTORY_WINDOW turns)
    """
    client = _get_client()
    context = _build_context(chunks)

    parts: list[str] = []
    if history:
        parts.append(_build_history_block(history))
    parts.append(context)
    parts.append(f"QUESTION: {question}")

    prompt = "\n\n".join(parts)

    for attempt in range(_MAX_RETRIES):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    temperature=0.0,
                    max_output_tokens=2048,
                ),
            )
            raw = response.text.strip()
            result = json.loads(raw)

            return {
                "answer": result.get("answer", ""),
                "found": bool(result.get("found", False)),
                "sources": result.get("sources", []),
            }

        except json.JSONDecodeError as e:
            logger.error("Gemini returned non-JSON: %s", e)
            raise RuntimeError(f"LLM returned malformed JSON: {e}") from e

        except genai_errors.ClientError as e:
            if _is_retryable(e) and attempt < _MAX_RETRIES - 1:
                delay = _RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(
                    "Gemini 503 on attempt %d/%d — retrying in %.1fs",
                    attempt + 1, _MAX_RETRIES, delay,
                )
                time.sleep(delay)
            else:
                logger.error("Gemini API client error: %s", e)
                raise RuntimeError(f"LLM unavailable: {e}") from e

        except Exception as e:
            logger.error("Gemini generation error: %s", e)
            raise RuntimeError(f"LLM error: {e}") from e


# ── Streaming ─────────────────────────────────────────────────────────────────

_NOT_FOUND_SENTINEL = "NOT_FOUND"
_SENTINEL_LEN = len(_NOT_FOUND_SENTINEL)


def stream_answer(
    question: str,
    chunks: list[dict],
    history: list[dict] | None = None,
) -> "Generator[dict, None, None]":
    """
    Sync generator for streaming answers token by token.

    Yields:
        {"type": "token", "text": str}   — answer text fragments (skipped if NOT_FOUND)
        {"type": "done",  "found": bool} — final sentinel with found status

    The caller is responsible for building sources from retrieved chunks.
    Raises RuntimeError on Gemini API failure.
    """
    from typing import Generator  # local import avoids circular issues

    client = _get_client()

    parts: list[str] = []
    if history:
        parts.append(_build_history_block(history))
    parts.append(_build_context(chunks))
    parts.append(f"QUESTION: {question}")
    prompt = "\n\n".join(parts)

    raw_stream = None
    for attempt in range(_MAX_RETRIES):
        try:
            raw_stream = client.models.generate_content_stream(
                model=GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=STREAM_SYSTEM_PROMPT,
                    temperature=0.0,
                    max_output_tokens=2048,
                ),
            )
            break  # stream opened successfully
        except genai_errors.ClientError as e:
            if _is_retryable(e) and attempt < _MAX_RETRIES - 1:
                delay = _RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(
                    "Gemini 503 on attempt %d/%d — retrying in %.1fs",
                    attempt + 1, _MAX_RETRIES, delay,
                )
                time.sleep(delay)
            else:
                logger.error("Gemini stream client error: %s", e)
                raise RuntimeError(f"LLM unavailable: {e}") from e
        except Exception as e:
            logger.error("Gemini stream error: %s", e)
            raise RuntimeError(f"LLM error: {e}") from e

    try:
        buffer = ""
        yielded_any = False

        for raw in raw_stream:
            if not raw.text:
                continue
            buffer += raw.text

            # Hold back enough chars to detect the NOT_FOUND sentinel at any split point.
            # Safe portion: everything except the last SENTINEL_LEN chars.
            if len(buffer) > _SENTINEL_LEN:
                safe, buffer = buffer[:-_SENTINEL_LEN], buffer[-_SENTINEL_LEN:]
                if safe:
                    yielded_any = True
                    yield {"type": "token", "text": safe}

        # Flush remaining buffer after stream ends
        if buffer:
            if buffer.strip() == _NOT_FOUND_SENTINEL:
                # Gemini said not found — discard, found stays False
                pass
            else:
                yielded_any = True
                yield {"type": "token", "text": buffer}

        found = yielded_any
        logger.info("Stream done — found=%s", found)
        yield {"type": "done", "found": found}

    except genai_errors.ClientError as e:
        logger.error("Gemini stream client error: %s", e)
        raise RuntimeError(f"LLM unavailable: {e}") from e

    except Exception as e:
        logger.error("Gemini stream error: %s", e)
        raise RuntimeError(f"LLM error: {e}") from e
