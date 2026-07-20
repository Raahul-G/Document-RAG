"""
ChromaDB vector store wrapper.
Uses an embedded (in-process) client — no separate server needed.
"""
from __future__ import annotations

import chromadb
from chromadb.config import Settings as ChromaSettings

from backend.config import settings

_client: chromadb.ClientAPI | None = None
_collection: chromadb.Collection | None = None

COLLECTION_NAME = "document_chunks"


def get_collection() -> chromadb.Collection:
    global _client, _collection
    if _client is None:
        _client = chromadb.PersistentClient(
            path=settings.chroma_path,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
    if _collection is None:
        _collection = _client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


def add_chunks(chunk_records: list[dict], embeddings: list[list[float]]) -> None:
    """Store chunks with their embeddings and metadata in ChromaDB."""
    collection = get_collection()
    collection.add(
        ids=[c["chroma_id"] for c in chunk_records],
        embeddings=embeddings,
        documents=[c["text"] for c in chunk_records],
        metadatas=[
            {
                "doc_id": c["doc_id"],
                "doc_name": c["doc_name"],
                "page_number": c["page_number"],
                "passage_index": c["passage_index"],
                "section_title": c["section_title"],
            }
            for c in chunk_records
        ],
    )


def query_chunks(
    query_embedding: list[float],
    n_results: int = 10,
    doc_ids: list[int] | None = None,
) -> list[dict]:
    """
    Semantic search. Optionally filter to specific document IDs.
    Returns list of {text, metadata, distance} dicts.
    """
    collection = get_collection()

    where = {"doc_id": {"$in": doc_ids}} if doc_ids else None

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=min(n_results, collection.count() or 1),
        where=where,
        include=["documents", "metadatas", "distances"],
    )

    chunks = []
    for text, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        chunks.append({"text": text, "metadata": meta, "score": 1 - dist})  # cosine → similarity

    return chunks


def delete_document_chunks(doc_id: int) -> None:
    """Remove all chunks belonging to a document."""
    collection = get_collection()
    results = collection.get(where={"doc_id": doc_id})
    if results["ids"]:
        collection.delete(ids=results["ids"])


def get_all_chunks() -> list[dict]:
    """Fetch all stored chunks (used to build BM25 index on startup)."""
    collection = get_collection()
    if collection.count() == 0:
        return []
    results = collection.get(include=["documents", "metadatas"])
    return [
        {"text": text, "metadata": meta}
        for text, meta in zip(results["documents"], results["metadatas"])
    ]


def reset_collection() -> None:
    """Delete and recreate the ChromaDB collection (used for embedding dimension migration)."""
    global _client, _collection
    if _client is None:
        _client = chromadb.PersistentClient(
            path=settings.chroma_path,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
    try:
        _client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    _collection = None
