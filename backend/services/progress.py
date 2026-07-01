"""
In-memory progress store for document ingestion pipeline.
Each document gets a progress entry keyed by doc_id.
Updated by the ingestion pipeline, read by the SSE endpoint.
"""
from __future__ import annotations

_store: dict[int, dict] = {}

STAGES = ["parsing", "chunking", "embedding", "storing", "done"]


def update(
    doc_id: int,
    stage: str,
    message: str,
    done: bool = False,
    error: str | None = None,
    percent: int = 0,
) -> None:
    _store[doc_id] = {
        "doc_id": doc_id,
        "stage": stage,
        "message": message,
        "done": done,
        "error": error,
        "percent": percent,
    }


def get(doc_id: int) -> dict | None:
    return _store.get(doc_id)


def clear(doc_id: int) -> None:
    _store.pop(doc_id, None)
