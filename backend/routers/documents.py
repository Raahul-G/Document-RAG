import hashlib
import shutil
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database import get_db
from backend.models import Document
from backend.schemas import DocumentListOut, DocumentOut
from backend.services import ingestion, vectorstore

router = APIRouter(prefix="/documents", tags=["documents"])

ALLOWED_TYPES = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
}


def _sha256(path: Path, chunk_size: int = 65536) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while data := f.read(chunk_size):
            h.update(data)
    return h.hexdigest()


def _run_ingestion(file_path: str, doc_id: int) -> None:
    """Background task: run ingestion pipeline with its own DB session."""
    from backend.database import SessionLocal
    db = SessionLocal()
    try:
        ingestion.ingest_document(file_path, doc_id, db)
    finally:
        db.close()


@router.post("/upload", response_model=DocumentOut, status_code=202)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    # Validate type
    file_type = ALLOWED_TYPES.get(file.content_type or "")
    if not file_type:
        raise HTTPException(status_code=415, detail="Only PDF and DOCX files are supported.")

    # Save to disk temporarily to hash
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = upload_dir / f"tmp_{file.filename}"

    with open(tmp_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    file_hash = _sha256(tmp_path)

    # Duplicate check
    existing = db.query(Document).filter(Document.file_hash == file_hash).first()
    if existing:
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=409,
            detail=f"Document already exists: '{existing.original_name}' (uploaded {existing.created_at.date()})",
        )

    # Rename to final path using hash prefix to avoid collisions
    final_path = upload_dir / f"{file_hash[:8]}_{file.filename}"
    tmp_path.rename(final_path)

    # Create DB record
    doc = Document(
        filename=final_path.name,
        original_name=file.filename,
        file_type=file_type,
        file_hash=file_hash,
        status="pending",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    # Kick off ingestion in background
    background_tasks.add_task(_run_ingestion, str(final_path), doc.id)

    return doc


@router.get("", response_model=DocumentListOut)
def list_documents(db: Session = Depends(get_db)):
    docs = db.query(Document).order_by(Document.created_at.desc()).all()
    return DocumentListOut(documents=docs)


@router.get("/{document_id}/status", response_model=DocumentOut)
def get_document_status(document_id: int, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.delete("/{document_id}")
def delete_document(document_id: int, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Remove from ChromaDB
    vectorstore.delete_document_chunks(document_id)

    # Remove file from disk
    file_path = Path(settings.upload_dir) / doc.filename
    file_path.unlink(missing_ok=True)

    # Remove from DB (cascades to chunks)
    db.delete(doc)
    db.commit()

    # Rebuild BM25
    from backend.services import bm25_index
    all_chunks = vectorstore.get_all_chunks()
    bm25_index.build_index(all_chunks)

    return {"ok": True}
