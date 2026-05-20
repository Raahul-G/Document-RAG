"""
Document ingestion pipeline: parse → chunk → embed → store.

Parsers:
  - PDF:  PyMuPDF (fitz) — fast, accurate page numbers, font-size header detection
  - DOCX: python-docx   — heading-style-aware, preserves document structure

Chunking:
  - Group content by detected section titles
  - Split oversized sections with character overlap (~17%)
  - Assign sequential passage_index per page

Pipeline:
  1. Parse → list of {page, text, category} elements
  2. Chunk by section boundaries + overlap
  3. Embed with nomic-embed-text (local)
  4. Store vectors in ChromaDB + metadata in SQLite
  5. Rebuild BM25 index
"""
from __future__ import annotations

import uuid
from pathlib import Path

import fitz  # PyMuPDF
from docx import Document as DocxDocument
from sqlalchemy.orm import Session

from backend.models import Chunk, Document
from backend.services import bm25_index, embeddings, progress as prog, vectorstore

# Chunking config
MAX_CHUNK_CHARS = 1500
OVERLAP_CHARS = 250      # ~17% overlap
MIN_SECTION_CHARS = 150  # merge tiny paragraphs below this
HEADER_FONT_THRESHOLD = 13.0  # PDF font size above which text is treated as a heading


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def _parse_pdf(file_path: str) -> list[dict]:
    """
    Extract structured elements from a PDF using PyMuPDF.
    Returns list of {page, text, category} where category is 'Title' or 'NarrativeText'.
    Font size heuristic identifies headings.
    """
    doc = fitz.open(file_path)
    elements: list[dict] = []

    for page_num, page in enumerate(doc, start=1):
        blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]

        for block in blocks:
            if block.get("type") != 0:  # skip non-text (images etc.)
                continue

            block_lines: list[str] = []
            max_font_size = 0.0

            for line in block.get("lines", []):
                line_parts: list[str] = []
                for span in line.get("spans", []):
                    text = span.get("text", "").strip()
                    if text:
                        line_parts.append(text)
                        max_font_size = max(max_font_size, span.get("size", 0.0))
                if line_parts:
                    block_lines.append(" ".join(line_parts))

            text = " ".join(block_lines).strip()
            if not text:
                continue

            # Heuristic: large font + short line → heading
            is_title = (
                max_font_size >= HEADER_FONT_THRESHOLD
                and len(text) < 200
                and not text.endswith(".")
            )
            elements.append({
                "page": page_num,
                "text": text,
                "category": "Title" if is_title else "NarrativeText",
            })

    doc.close()
    return elements


def _parse_docx(file_path: str) -> list[dict]:
    """
    Extract structured elements from a DOCX using python-docx.
    Uses Word heading styles to detect section titles.
    Page numbers are estimated (Word doesn't expose real page breaks easily).
    """
    doc = DocxDocument(file_path)
    elements: list[dict] = []
    estimated_page = 1
    char_count = 0
    CHARS_PER_PAGE = 2000  # rough estimate for page number tracking

    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue

        style_name = (para.style.name if para.style else "").lower()
        is_heading = "heading" in style_name or style_name == "title"

        char_count += len(text)
        estimated_page = max(1, char_count // CHARS_PER_PAGE + 1)

        elements.append({
            "page": estimated_page,
            "text": text,
            "category": "Title" if is_heading else "NarrativeText",
        })

    return elements


def _parse(file_path: str, file_type: str) -> list[dict]:
    if file_type == "pdf":
        return _parse_pdf(file_path)
    if file_type == "docx":
        return _parse_docx(file_path)
    raise ValueError(f"Unsupported file type: {file_type}")


# ---------------------------------------------------------------------------
# Chunker
# ---------------------------------------------------------------------------

def _flush_chunk(
    text: str,
    page: int,
    section: str,
    doc_id: int,
    doc_name: str,
    page_counters: dict[int, int],
    records: list[dict],
) -> None:
    """Save a text block as one or more chunk records, splitting at MAX_CHUNK_CHARS."""
    text = text.strip()
    if not text:
        return

    start = 0
    while start < len(text):
        end = start + MAX_CHUNK_CHARS

        # Snap end back to last word boundary to avoid splitting mid-word
        if end < len(text):
            boundary = end
            while boundary > start and not text[boundary].isspace():
                boundary -= 1
            if boundary > start:
                end = boundary

        fragment = text[start:end].strip()
        if not fragment:
            break

        page_counters.setdefault(page, 0)
        page_counters[page] += 1

        records.append({
            "chroma_id": str(uuid.uuid4()),
            "doc_id": doc_id,
            "doc_name": doc_name,
            "page_number": page,
            "passage_index": page_counters[page],
            "section_title": section,
            "text": fragment,
        })

        # Move forward with overlap so boundary content appears in both chunks.
        # Snap the overlap start forward to the next full word to avoid starting mid-word.
        next_start = end - OVERLAP_CHARS
        if 0 < next_start < len(text):
            while next_start < len(text) and not text[next_start].isspace():
                next_start += 1
            start = next_start + 1 if next_start < len(text) else len(text)
        else:
            start = next_start


def _chunk(elements: list[dict], doc_id: int, doc_name: str) -> list[dict]:
    """
    Chunk elements by section boundaries.
    Sections start at each Title element. Oversized sections are split with overlap.
    """
    records: list[dict] = []
    page_counters: dict[int, int] = {}

    current_section = ""
    current_text = ""
    current_page = 1

    for el in elements:
        if el["category"] == "Title":
            # Flush current section before starting a new one
            if len(current_text.strip()) >= MIN_SECTION_CHARS:
                _flush_chunk(current_text, current_page, current_section, doc_id, doc_name, page_counters, records)
                carry = ""
            else:
                # Section is below the minimum — carry its text forward so it is
                # not silently lost; it will be prepended to the next section.
                carry = current_text.rstrip() + "\n\n" if current_text.strip() else ""

            current_section = el["text"]
            current_page = el["page"]
            current_text = carry + el["text"] + "\n\n"
        else:
            current_page = el["page"]
            current_text += el["text"] + "\n"

    # Flush the last section
    if current_text.strip():
        _flush_chunk(current_text, current_page, current_section, doc_id, doc_name, page_counters, records)

    return records


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def ingest_document(file_path: str, doc_id: int, db: Session) -> int:
    """
    Full ingestion pipeline for one document.
    Updates Document.status in the DB throughout.
    Returns number of chunks created.
    """
    doc: Document | None = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise ValueError(f"Document {doc_id} not found")

    try:
        doc.status = "processing"
        db.commit()

        # 1. Parse
        prog.update(doc_id, "parsing", f"Parsing {doc.file_type.upper()}...")
        elements = _parse(file_path, doc.file_type)

        pages = {el["page"] for el in elements}
        doc.page_count = max(pages) if pages else 0
        db.commit()

        # 2. Chunk
        prog.update(doc_id, "chunking", f"Chunking {len(elements)} elements into sections...")
        chunk_records = _chunk(elements, doc_id, doc.original_name)

        if not chunk_records:
            doc.status = "indexed"
            db.commit()
            prog.update(doc_id, "done", "Indexed — no content extracted.", done=True)
            return 0

        # 3. Embed
        prog.update(doc_id, "embedding", f"Embedding {len(chunk_records)} chunks (first run downloads model)...")
        texts = [c["text"] for c in chunk_records]
        vectors = embeddings.embed_documents(texts)

        # 4a. Store in ChromaDB
        prog.update(doc_id, "storing", "Storing in vector database...")
        vectorstore.add_chunks(chunk_records, vectors)

        # 4b. Store chunk metadata in SQLite
        db.add_all([
            Chunk(
                document_id=doc_id,
                page_number=c["page_number"],
                passage_index=c["passage_index"],
                section_title=c["section_title"],
                text=c["text"],
                chroma_id=c["chroma_id"],
            )
            for c in chunk_records
        ])

        doc.status = "indexed"
        db.commit()

        # 5. Rebuild BM25 index
        all_chunks = vectorstore.get_all_chunks()
        bm25_index.build_index(all_chunks)

        prog.update(doc_id, "done", f"Indexed — {len(chunk_records)} chunks ready.", done=True)
        return len(chunk_records)

    except Exception as e:
        doc.status = "failed"
        db.commit()
        prog.update(doc_id, "failed", str(e), done=True, error=str(e))
        raise e
