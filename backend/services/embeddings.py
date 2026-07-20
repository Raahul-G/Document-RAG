"""
Local embedding model using nomic-embed-text-v1.5 via FastEmbed (ONNX int8-quantized).
Model is lazy-loaded on first use to keep server startup fast.

nomic-embed-text-v1.5 requires task prefixes (trained with them):
  Documents: "search_document: " + text
  Queries:   "search_query: " + text
"""
from __future__ import annotations

from fastembed import TextEmbedding

_model: TextEmbedding | None = None

MODEL_NAME = "nomic-ai/nomic-embed-text-v1.5"


def _get_model() -> TextEmbedding:
    global _model
    if _model is None:
        _model = TextEmbedding(MODEL_NAME)
    return _model


def embed_documents(texts: list[str]) -> list[list[float]]:
    """Embed document chunks with nomic document task prefix."""
    model = _get_model()
    prefixed = ["search_document: " + t for t in texts]
    return [v.tolist() for v in model.embed(prefixed)]


def embed_query(text: str) -> list[float]:
    """Embed a search query with nomic query task prefix."""
    model = _get_model()
    result = list(model.embed(["search_query: " + text]))
    return result[0].tolist()
