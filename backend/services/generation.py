"""
Answer generation using Gemini 1.5 Pro via google-genai SDK.

Rules enforced via system prompt:
  - Answer ONLY from provided passages (no external knowledge)
  - Return structured JSON: {answer, found, sources[]}
  - If answer not in passages → found: false, empty answer
"""
from __future__ import annotations

import json
import logging

from google import genai
from google.genai import types

from backend.config import settings

logger = logging.getLogger(__name__)

_client: genai.Client | None = None
GEMINI_MODEL = "gemini-1.5-pro"

SYSTEM_PROMPT = """You are a precise document analysis assistant.

Your ONLY job is to answer questions using the document passages provided to you.

STRICT RULES:
1. Answer ONLY using information found in the provided passages.
2. Do NOT use any external knowledge, training data, or assumptions.
3. If the answer is NOT found in the passages, set "found" to false and "answer" to an empty string.
4. Always cite the exact passage(s) you used in "sources".
5. Return ONLY valid JSON — no extra text, no markdown fences, no explanation outside the JSON.

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


def generate_answer(question: str, chunks: list[dict]) -> dict:
    """
    Call Gemini 1.5 Pro with the question + retrieved passages.
    Returns parsed {answer, found, sources} dict.
    """
    client = _get_client()
    context = _build_context(chunks)
    prompt = f"{context}\n\nQUESTION: {question}"

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
        return {"answer": "", "found": False, "sources": []}

    except Exception as e:
        logger.error("Gemini generation error: %s", e)
        raise
