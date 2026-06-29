"""
Answer generation using a local GGUF model via llama-cpp-python.

Rules enforced via system prompt:
  - Answer ONLY from provided passages (no external knowledge)
  - Return structured JSON: {answer, found, sources[]}
  - If answer not in passages → found: false, empty answer
"""
from __future__ import annotations

import json
import logging
import re

from llama_cpp import Llama, LlamaGrammar

from backend.config import settings

logger = logging.getLogger(__name__)

_llm: Llama | None = None

_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "found": {"type": "boolean"},
        "sources": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "doc_name": {"type": "string"},
                    "page": {"type": "integer"},
                    "passage_index": {"type": "integer"},
                    "section_title": {"type": "string"},
                    "text": {"type": "string"},
                },
                "required": ["doc_name", "page", "passage_index", "section_title", "text"],
            },
        },
    },
    "required": ["answer", "found", "sources"],
}


# ── Query rewriting prompt ────────────────────────────────────────────────────
_REWRITE_SYSTEM_PROMPT = """You are a search query rewriter for a document retrieval system.

Given a conversation history and a follow-up question, rewrite the question into a fully self-contained search query that can be understood without any prior context.

Rules:
- Resolve all pronouns and references (it, that, they, the previous one, those, etc.) using the conversation history
- Include key entities, topics, and concepts from previous turns if the question references them
- Output ONLY the rewritten query — no explanation, no preamble, no quotes
- If the question is already fully self-contained (no references to prior turns), output it unchanged"""


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


def _get_llm() -> Llama:
    global _llm
    if _llm is None:
        _llm = Llama(
            model_path=settings.llm_model_path,
            n_ctx=settings.llm_n_ctx,
            n_threads=settings.llm_n_threads,
            n_gpu_layers=settings.llm_n_gpu_layers,
            verbose=False,
        )
    return _llm


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


def _repair_json(raw: str) -> dict:
    """
    Try to parse JSON from raw LLM output, with fallback strategies.
    Raises ValueError if all strategies fail.
    """
    # 1. Direct parse
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # 2. Strip markdown fences
    stripped = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`").strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    # 3. Regex extract first {...} block
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not parse JSON from LLM output: {raw[:200]!r}")


def rewrite_query(question: str, history: list[dict]) -> str:
    """
    Rewrite a follow-up question into a standalone search query using conversation history.
    Resolves pronouns and anaphoric references so retrieval gets a self-contained query.

    Returns the original question unchanged when no history is provided (first turn).
    Falls back to the original question on any LLM error.
    """
    if not history:
        return question

    llm = _get_llm()

    history_text = "\n".join(
        f"User: {t['question']}\nAssistant: {t['answer']}" for t in history
    )
    messages = [
        {"role": "system", "content": _REWRITE_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Conversation history:\n{history_text}\n\n"
                f"Follow-up question: {question}\n\n"
                "Rewritten query:"
            ),
        },
    ]

    try:
        response = llm.create_chat_completion(
            messages=messages,
            temperature=0.0,
            max_tokens=128,
            stream=False,
        )
        rewritten = response["choices"][0]["message"]["content"].strip()
        return rewritten if rewritten else question
    except Exception as e:
        logger.warning("Query rewriting failed, using original question: %s", e)
        return question


def generate_answer(
    question: str,
    chunks: list[dict],
    history: list[dict] | None = None,
) -> dict:
    """
    Call local LLM with the question + retrieved passages + optional conversation history.
    Returns parsed {answer, found, sources} dict.

    history: list of {question, answer} dicts ordered oldest → newest (max HISTORY_WINDOW turns)
    """
    llm = _get_llm()
    context = _build_context(chunks)

    parts: list[str] = []
    if history:
        parts.append(_build_history_block(history))
    parts.append(context)
    parts.append(f"QUESTION: {question}")

    user_content = "\n\n".join(parts)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    try:
        grammar = LlamaGrammar.from_json_schema(json.dumps(_JSON_SCHEMA))
        response = llm.create_chat_completion(
            messages=messages,
            grammar=grammar,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            stream=False,
        )
        raw = response["choices"][0]["message"]["content"].strip()
        result = _repair_json(raw)

        return {
            "answer": result.get("answer", ""),
            "found": bool(result.get("found", False)),
            "sources": result.get("sources", []),
        }

    except ValueError as e:
        logger.error("LLM returned malformed JSON: %s", e)
        raise RuntimeError(f"LLM returned malformed JSON: {e}") from e

    except Exception as e:
        logger.error("LLM generation error: %s", e)
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
    Raises RuntimeError on LLM failure.
    """
    llm = _get_llm()

    parts: list[str] = []
    if history:
        parts.append(_build_history_block(history))
    parts.append(_build_context(chunks))
    parts.append(f"QUESTION: {question}")
    user_content = "\n\n".join(parts)

    messages = [
        {"role": "system", "content": STREAM_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    try:
        raw_stream = llm.create_chat_completion(
            messages=messages,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            stream=True,
        )
    except Exception as e:
        logger.error("LLM stream error: %s", e)
        raise RuntimeError(f"LLM error: {e}") from e

    try:
        buffer = ""
        yielded_any = False

        for chunk in raw_stream:
            delta = chunk["choices"][0].get("delta", {})
            token = delta.get("content") or ""
            if not token:
                continue
            buffer += token

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
                # LLM said not found — discard, found stays False
                pass
            else:
                yielded_any = True
                yield {"type": "token", "text": buffer}

        found = yielded_any
        logger.info("Stream done — found=%s", found)
        yield {"type": "done", "found": found}

    except Exception as e:
        logger.error("LLM stream error: %s", e)
        raise RuntimeError(f"LLM error: {e}") from e
