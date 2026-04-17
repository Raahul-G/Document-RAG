"""
Local embedding model using nomic-embed-text-v1.5 via sentence-transformers.
Model is lazy-loaded on first use to keep server startup fast.
"""
from __future__ import annotations

from sentence_transformers import SentenceTransformer

_model: SentenceTransformer | None = None

MODEL_NAME = "nomic-ai/nomic-embed-text-v1.5"


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(MODEL_NAME, trust_remote_code=True)
    return _model


def embed_documents(texts: list[str]) -> list[list[float]]:
    """Embed document chunks. Uses 'search_document:' prefix as required by nomic."""
    model = _get_model()
    prefixed = [f"search_document: {t}" for t in texts]
    return model.encode(prefixed, normalize_embeddings=True, show_progress_bar=False).tolist()


def embed_query(text: str) -> list[float]:
    """Embed a search query. Uses 'search_query:' prefix as required by nomic."""
    model = _get_model()
    prefixed = f"search_query: {text}"
    return model.encode(prefixed, normalize_embeddings=True, show_progress_bar=False).tolist()
