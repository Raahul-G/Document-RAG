import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

logging.basicConfig(level=logging.INFO, format="%(name)s | %(levelname)s | %(message)s")
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.config import settings
from backend.database import Base, engine
from backend.routers import documents, query, sessions, snippets

_llm_ready = False


def _maybe_migrate_chroma() -> None:
    """
    Detect stale vectors with wrong embedding dimension and clear all data.
    Must run before any BM25 or vector reads in the lifespan block.
    """
    from backend.database import SessionLocal
    from backend.models import Chunk
    from backend.services import bm25_index, vectorstore

    try:
        collection = vectorstore.get_collection()
        if collection.count() == 0:
            return  # empty — nothing to migrate

        result = collection.get(limit=1, include=["embeddings"])
        embeddings = result.get("embeddings") or []
        if not embeddings:
            return

        dim = len(embeddings[0])
        if dim == 768:
            return  # correct dimension for nomic-embed-text-v1.5

        print(f"Migration: detected {dim}-dim vectors (expected 768). Clearing stale data...")
        vectorstore.reset_collection()
        bm25_index.invalidate_pickle()

        db = SessionLocal()
        try:
            db.query(Chunk).delete()
            db.commit()
        finally:
            db.close()

        print("Migration: stale data cleared. Re-ingest documents after restart.")
    except Exception as e:
        print(f"Migration guard error (non-fatal): {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Directories and DB tables
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.chroma_path).mkdir(parents=True, exist_ok=True)
    Path("data").mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)

    # 2. Migration guard — must complete before any BM25 or vector reads
    _maybe_migrate_chroma()

    # 3. BM25 load-or-build
    from backend.services import bm25_index, vectorstore
    if bm25_index.load_index():
        print(f"BM25 index loaded from disk ({len(bm25_index._corpus)} chunks)")
    else:
        existing_chunks = vectorstore.get_all_chunks()
        bm25_index.build_index(existing_chunks)
        print(f"BM25 index built: {len(existing_chunks)} chunks loaded")

    # 4. Warm up the local LLM so the first query has no cold-start delay
    global _llm_ready
    from backend.services.generation import _get_llm
    model_path = settings.llm_model_path
    if Path(model_path).exists():
        print(f"Loading LLM from {model_path} ...")
        _get_llm()
        print("LLM ready.")
    else:
        print(f"Warning: LLM model not found at {model_path} — will load on first query.")
    _llm_ready = True

    yield


app = FastAPI(title="Document RAG", version="0.1.0", lifespan=lifespan)

_origins_raw = os.getenv("CORS_ORIGINS", "http://localhost:5173")
_allow_credentials = _origins_raw != "*"
_origins = ["*"] if _origins_raw == "*" else [o.strip() for o in _origins_raw.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents.router, prefix="/api")
app.include_router(query.router, prefix="/api")
app.include_router(sessions.router, prefix="/api")
app.include_router(snippets.router, prefix="/api")


@app.get("/api/system/status")
def system_status():
    return {"llm_ready": _llm_ready}

# Serve React build in production
frontend_dist = Path("frontend/dist")
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="static")
