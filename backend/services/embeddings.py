"""
Local embedding model using all-MiniLM-L6-v2 via sentence-transformers.
Model is lazy-loaded on first use to keep server startup fast.
"""
from __future__ import annotations

from sentence_transformers import SentenceTransformer

_model: SentenceTransformer | None = None

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def embed_documents(texts: list[str]) -> list[list[float]]:
    """Embed document chunks."""
    model = _get_model()
    return model.encode(texts, normalize_embeddings=True, show_progress_bar=False).tolist()


def embed_query(text: str) -> list[float]:
    """Embed a search query."""
    model = _get_model()
    return model.encode(text, normalize_embeddings=True, show_progress_bar=False).tolist()
