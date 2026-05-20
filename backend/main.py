import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

logging.basicConfig(level=logging.INFO, format="%(name)s | %(levelname)s | %(message)s")
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.config import settings
from backend.database import Base, engine
from backend.routers import documents, query, sessions, snippets


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create required directories
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.chroma_path).mkdir(parents=True, exist_ok=True)
    Path("data").mkdir(parents=True, exist_ok=True)

    # Create all DB tables
    Base.metadata.create_all(bind=engine)

    # Build BM25 index from existing chunks
    from backend.services import bm25_index, vectorstore
    existing_chunks = vectorstore.get_all_chunks()
    bm25_index.build_index(existing_chunks)
    print(f"BM25 index built: {len(existing_chunks)} chunks loaded")

    yield


app = FastAPI(title="Document RAG", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents.router, prefix="/api")
app.include_router(query.router, prefix="/api")
app.include_router(sessions.router, prefix="/api")
app.include_router(snippets.router, prefix="/api")

# Serve React build in production
frontend_dist = Path("frontend/dist")
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="static")
