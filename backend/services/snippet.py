"""
Render a PDF page as PNG with the cited passage highlighted.
"""
from __future__ import annotations

import functools
import re
import string
from pathlib import Path

import fitz  # PyMuPDF

from backend.config import settings
from backend.models import Chunk, Document

# How many words to take from passage text for fitz search
_SEARCH_WORDS = 6
# Word start offsets to try when the first word is a fragment
_WORD_OFFSETS = (0, 1, 2, 3, 5, 10)
# Skip words shorter than this (likely a fragment at a chunk boundary)
_MIN_WORD_LEN = 2
# Phrase must be at least this many chars to be a reliable search target
_MIN_PHRASE_LEN = 12  # lowered from 15 — handles short section headings
# Page-offset window to try when search drifts from the stored page number
PAGE_SEARCH_WINDOW = (-2, -1, 0, 1, 2)
# Estimated characters per line used when end anchor is not found
_CHARS_PER_LINE = 80
# Horizontal margin added around the start-phrase x-range for column detection
_COL_X_MARGIN = 30

# PDF ligature → expanded form (ﬁ, ﬂ, etc.)
_LIGATURES: dict[str, str] = {
    "\ufb00": "ff",
    "\ufb01": "fi",
    "\ufb02": "fl",
    "\ufb03": "ffi",
    "\ufb04": "ffl",
    "\ufb05": "st",
    "\ufb06": "st",
}


class SnippetError(Exception):
    """Raised for expected failures (doc not found, DOCX, page OOB, …)."""


# ---------------------------------------------------------------------------
# Text normalisation helpers
# ---------------------------------------------------------------------------

def _normalise(text: str) -> str:
    """
    Normalise text so ingested chunk text matches what PyMuPDF extracts from
    the PDF's raw content stream.

    - Expands common ligatures (ﬁ→fi, ﬂ→fl, ﬀ→ff, …)
    - Removes soft hyphens (U+00AD) that PDFs embed for line-break hints
    - Collapses any run of whitespace to a single space
    """
    for lig, replacement in _LIGATURES.items():
        text = text.replace(lig, replacement)
    text = text.replace("\u00ad", "")       # soft hyphen
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _strip_punct(word: str) -> str:
    """Strip leading/trailing punctuation for tolerant word comparison."""
    return word.strip(string.punctuation)


# ---------------------------------------------------------------------------
# Phrase builders
# ---------------------------------------------------------------------------

def _make_search_phrase(text: str, n: int = _SEARCH_WORDS) -> str:
    """First reliable n-word phrase, skipping leading word fragments."""
    text = _normalise(text)
    words = text.split()
    for offset in _WORD_OFFSETS:
        if offset >= len(words):
            break
        phrase_words = words[offset : offset + n]
        if not phrase_words:
            continue
        if len(phrase_words[0]) < _MIN_WORD_LEN:
            continue  # skip fragment at this offset, try next
        phrase = " ".join(phrase_words)
        if len(phrase) >= _MIN_PHRASE_LEN:
            return phrase
    return ""  # nothing usable found


def _last_search_phrase(text: str, n: int = _SEARCH_WORDS) -> str:
    """Last reliable n-word phrase, skipping trailing word fragments."""
    text = _normalise(text)
    words = text.split()
    total = len(words)
    for offset in _WORD_OFFSETS:
        end_idx = total - offset
        if end_idx <= 0:
            break
        start_idx = max(0, end_idx - n)
        phrase_words = words[start_idx:end_idx]
        if not phrase_words:
            continue
        if len(phrase_words[-1]) < _MIN_WORD_LEN:
            continue  # trailing fragment, try earlier offset
        phrase = " ".join(phrase_words)
        if len(phrase) >= _MIN_PHRASE_LEN:
            return phrase
    return ""  # nothing usable found


# ---------------------------------------------------------------------------
# Page search helpers
# ---------------------------------------------------------------------------

def _word_level_search(page: fitz.Page, phrase: str) -> list[fitz.Rect]:
    """
    Fall-back phrase search that matches word-by-word against the fitz word list.
    Tolerant of:
      - Whitespace differences (double-space in raw PDF vs single-space in chunk)
      - Punctuation attached to words ("word," vs "word")
    """
    target = [_strip_punct(w) for w in phrase.lower().split()]
    if not target:
        return []
    n = len(target)
    word_list = page.get_text("words")  # (x0, y0, x1, y1, word, block, line, word_no)
    if len(word_list) < n:
        return []
    for i in range(len(word_list) - n + 1):
        if all(
            _strip_punct(word_list[i + j][4].lower()) == target[j]
            for j in range(n)
        ):
            return [fitz.Rect(word_list[i + j][:4]) for j in range(n)]
    return []


def _search_phrase_on_page(page: fitz.Page, phrase: str) -> list[fitz.Rect]:
    """
    Search for *phrase* on *page*.

    1. Normalise phrase (ligatures, soft hyphens, whitespace).
    2. Try fitz's native exact search (fast).
    3. Fall back to word-level matching (punctuation + whitespace tolerant).
    """
    normalised = _normalise(phrase)
    rects = page.search_for(normalised)
    if rects:
        return rects
    return _word_level_search(page, normalised)


# ---------------------------------------------------------------------------
# End-y estimation when end anchor is not found on the page
# ---------------------------------------------------------------------------

def _estimate_end_y(
    start_y: float,
    start_rects: list[fitz.Rect],
    passage_text: str,
    page_height: float,
) -> float:
    """
    Estimate where the passage ends when the end-phrase search fails.

    Uses average line height from the start anchor rects and the character
    count of the passage to guess how many lines it spans.  Always clamps to
    the page bottom so we never go out of bounds.
    """
    line_height = (
        max(r.y1 - r.y0 for r in start_rects) if start_rects else 12.0
    )
    estimated_lines = max(3, len(passage_text) // _CHARS_PER_LINE)
    return min(start_y + estimated_lines * line_height, page_height)


# ---------------------------------------------------------------------------
# Main render function
# ---------------------------------------------------------------------------

@functools.lru_cache(maxsize=50)
def _render_cached(filename: str, fitz_page_idx: int, passage_text: str) -> bytes:
    """
    Open *filename* (relative to upload_dir), render page *fitz_page_idx*,
    highlight *passage_text*, and return PNG bytes.

    Improvements over naive implementation:
      - Normalises text before every search (ligatures, soft hyphens)
      - ±2 page drift window for page-number misestimates
      - Multi-offset start phrase (skips chunk-boundary fragments)
      - Word-level punctuation-tolerant fallback search
      - End-anchor estimation instead of full-page-bottom fallback
      - X-range constraint for multi-column PDF layouts

    Results are cached by (filename, page_idx, passage_text) — ~55 KB/entry → max ~2.75 MB RAM.
    """
    pdf_path = Path(settings.upload_dir) / filename
    doc = fitz.open(str(pdf_path))

    page_count = len(doc)
    if fitz_page_idx < 0 or fitz_page_idx >= page_count:
        doc.close()
        raise SnippetError(f"Page index {fitz_page_idx} out of range (0–{page_count - 1})")

    words = passage_text.split()
    start_rects: list[fitz.Rect] = []
    render_page_idx = fitz_page_idx

    # --- STEP 1: find start anchor (offset + page-drift strategy) ---
    for word_offset in _WORD_OFFSETS:
        phrase_words = words[word_offset : word_offset + _SEARCH_WORDS]
        if not phrase_words or len(phrase_words[0]) < _MIN_WORD_LEN:
            continue
        phrase = " ".join(phrase_words)
        if len(phrase) < _MIN_PHRASE_LEN:
            continue

        for page_offset in PAGE_SEARCH_WINDOW:
            candidate = fitz_page_idx + page_offset
            if 0 <= candidate < page_count:
                rects = _search_phrase_on_page(doc[candidate], phrase)
                if rects:
                    render_page_idx = candidate
                    start_rects = rects
                    break
        if start_rects:
            break

    page = doc[render_page_idx]

    if start_rects:
        # --- STEP 2: find end anchor on the same page ---
        last_phrase = _last_search_phrase(passage_text)
        end_rects = _search_phrase_on_page(page, last_phrase) if last_phrase else []

        # --- STEP 3: compute y-band ---
        start_y = min(r.y0 for r in start_rects) - 1  # small tolerance

        if end_rects:
            end_y = max(r.y1 for r in end_rects) + 1
        else:
            # FIX: estimate end_y from char count rather than falling back to
            # the full page bottom, which caused the entire page to be highlighted
            # whenever a chunk spans two pages or its end phrase wasn't searchable.
            end_y = _estimate_end_y(start_y, start_rects, passage_text, page.rect.y1)

        # --- STEP 4: collect words in y-band ---
        word_entries = page.get_text("words")  # (x0, y0, x1, y1, word, …)
        band_words = [w for w in word_entries if w[1] >= start_y and w[3] <= end_y]

        # --- STEP 5: apply x-column constraint only for true multi-column layouts ---
        #
        # Detection: in a single-column PDF many individual words span the page
        # centerline (w[0] < mid < w[2]).  In a two-column PDF every word stays
        # entirely within its column — no word crosses the centerline.
        #
        # We do NOT use phrase_span < 50% because 6 search words routinely cover
        # less than half the page width even in single-column documents, which
        # caused the right portion of every wrapped line to be dropped.
        page_w = page.rect.width
        phrase_x0 = min(r.x0 for r in start_rects)
        phrase_x1 = max(r.x1 for r in start_rects)
        page_mid = page_w / 2.0

        is_single_column = any(
            w[0] < page_mid and w[2] > page_mid for w in band_words
        )

        if is_single_column:
            # Single-column layout — no x constraint
            highlight_rects = [fitz.Rect(w[:4]) for w in band_words]
        else:
            # Multi-column detected — constrain to the column the start phrase is in
            phrase_center = (phrase_x0 + phrase_x1) / 2.0
            if phrase_center < page_mid:
                highlight_rects = [
                    fitz.Rect(w[:4]) for w in band_words
                    if w[0] < page_mid + _COL_X_MARGIN
                ]
            else:
                highlight_rects = [
                    fitz.Rect(w[:4]) for w in band_words
                    if w[2] > page_mid - _COL_X_MARGIN
                ]

        # Fall back to start_rects only if spatial collection returned nothing
        if not highlight_rects:
            highlight_rects = start_rects

        annot = page.add_highlight_annot(highlight_rects)
        annot.set_colors({"stroke": [1.0, 0.95, 0.0]})
        annot.update()

    png_bytes = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5)).tobytes("png")
    doc.close()
    return png_bytes


def render_page_png(
    doc_name: str,
    page_num: int,
    passage_text: str,
    db,
    passage_index: int | None = None,
) -> bytes:
    """
    Public API: look up *doc_name* in DB, validate it's a PDF, render and
    return PNG bytes with the passage highlighted.

    Args:
        doc_name:      Document.original_name value (e.g. "2022_AEUC.pdf")
        page_num:      1-based page number as stored in the chunk metadata
        passage_text:  Raw passage text (used to derive search phrase)
        db:            SQLAlchemy Session
        passage_index: Optional 1-based passage index on the page.  When
                       provided, the stored chunk text is loaded from the DB
                       and used instead of *passage_text*, bypassing any
                       LLM-rewritten text that the caller may have passed in.

    Raises:
        SnippetError: document not found, not a PDF, or page out of range
    """
    doc: Document | None = (
        db.query(Document).filter(Document.original_name == doc_name).first()
    )
    if doc is None:
        raise SnippetError(f"Document not found: {doc_name!r}")
    if doc.file_type != "pdf":
        raise SnippetError(f"Snippet rendering is only supported for PDF files (got {doc.file_type!r})")

    # If a passage_index is supplied, load the true stored chunk text from the
    # DB.  This is more reliable than the text passed by the caller, which in
    # the non-streaming path may be LLM-paraphrased.
    if passage_index is not None:
        chunk: Chunk | None = (
            db.query(Chunk)
            .filter(
                Chunk.document_id == doc.id,
                Chunk.page_number == page_num,
                Chunk.passage_index == passage_index,
            )
            .first()
        )
        if chunk is not None:
            passage_text = chunk.text

    return _render_cached(doc.filename, page_num - 1, passage_text)
