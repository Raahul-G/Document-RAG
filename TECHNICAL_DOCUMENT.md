
# Document-RAG: Technical Design Document

**Project**: Document-RAG
**Version**: Milestone 7
**Author**: Raahul G
**Date**: May 2026

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [System Architecture](#2-system-architecture)
3. [Tech Stack](#3-tech-stack)
4. [Data Storage Layer](#4-data-storage-layer)
5. [Document Ingestion Pipeline](#5-document-ingestion-pipeline)
6. [The RAG Retrieval System](#6-the-rag-retrieval-system)
   - 6.1 [Embedding & Vector Search](#61-embedding--vector-search)
   - 6.2 [BM25 Keyword Search](#62-bm25-keyword-search)
   - 6.3 [Hybrid Merge & Deduplication](#63-hybrid-merge--deduplication)
   - 6.4 [Gate 1 — Coverage Check](#64-gate-1--coverage-check)
   - 6.5 [Cross-Encoder Reranking](#65-cross-encoder-reranking)
   - 6.6 [Combined Scoring](#66-combined-scoring)
   - 6.7 [Dynamic Chunk Selection](#67-dynamic-chunk-selection)
7. [Answer Generation](#7-answer-generation)
8. [Snippet Rendering & Highlighting](#8-snippet-rendering--highlighting)
9. [Streaming Architecture](#9-streaming-architecture)
10. [Frontend Architecture](#10-frontend-architecture)
11. [API Reference](#11-api-reference)
12. [End-to-End Flow](#12-end-to-end-flow)
13. [Performance Characteristics](#13-performance-characteristics)
14. [Configuration & Environment](#14-configuration--environment)

---

## 1. Project Overview

Document-RAG is a locally-hosted Retrieval-Augmented Generation (RAG) system. Users upload PDF or DOCX documents and ask natural-language questions. The system retrieves only the most relevant passages from those documents, passes them to a Gemini LLM, and returns a grounded answer — meaning the model is explicitly instructed to cite only what appears in the uploaded documents, never its training knowledge.

The system is designed around three core principles:

- **Precision over recall at generation time** — only genuinely relevant chunks reach the LLM, not a fixed five chunks regardless of quality.
- **Transparency** — every answer includes source citations that link back to the exact PDF page with a yellow highlight showing the cited passage.
- **Local-first** — embeddings, vector storage, BM25, and reranking all run in-process. Only Gemini calls leave the machine.

---

## 2. System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                        Frontend                         │
│   React 19 + Tailwind CSS + Vite                        │
│   ChatInterface  │  ChatSidebar  │  Upload / Library    │
└────────────────────────┬────────────────────────────────┘
                         │  HTTP / SSE
┌────────────────────────▼────────────────────────────────┐
│                     FastAPI Backend                     │
│                                                         │
│  /api/documents   /api/query   /api/sessions            │
│  /api/snippets                                          │
│                                                         │
│  ┌──────────────────────────────────────────────────┐   │
│  │               RAG Pipeline                       │   │
│  │                                                  │   │
│  │  Ingestion                  Retrieval            │   │
│  │  ─────────                  ─────────            │   │
│  │  Parse PDF/DOCX             Embed query          │   │
│  │  Detect headings            Vector search        │   │
│  │  Chunk (overlap)            BM25 search          │   │
│  │  Embed chunks               Merge + dedupe       │   │
│  │  Store in ChromaDB          Gate 1 check         │   │
│  │  Store in SQLite            Cross-encoder rank   │   │
│  │  Rebuild BM25               Dynamic selection    │   │
│  │                                                  │   │
│  │  Generation                 Snippet              │   │
│  │  ──────────                 ───────              │   │
│  │  Build prompt               Find text on page    │   │
│  │  Gemini 2.5-Flash           Highlight y-band     │   │
│  │  Streaming SSE              Render PNG           │   │
│  └──────────────────────────────────────────────────┘   │
│                                                         │
│  ┌──────────────┐   ┌─────────────┐   ┌─────────────┐  │
│  │   SQLite DB  │   │  ChromaDB   │   │   /uploads  │  │
│  │  (metadata)  │   │  (vectors)  │   │   (files)   │  │
│  └──────────────┘   └─────────────┘   └─────────────┘  │
└─────────────────────────────────────────────────────────┘
```

---

## 3. Tech Stack

### Backend

| Component | Library / Service | Version | Purpose |
|---|---|---|---|
| API framework | FastAPI | ≥ 0.115 | REST endpoints, SSE streaming |
| ASGI server | Uvicorn (standard) | ≥ 0.32 | HTTP server |
| Relational DB | SQLite + SQLAlchemy | ≥ 2.0 | Document & session metadata |
| Vector store | ChromaDB | ≥ 1.5.7 | Persistent semantic index |
| Embeddings | sentence-transformers | ≥ 5.4.1 | nomic-embed-text-v1.5 |
| Cross-encoder | sentence-transformers | ≥ 5.4.1 | ms-marco-MiniLM-L-6-v2 |
| Keyword search | rank-bm25 | ≥ 0.2.2 | In-memory BM25Okapi |
| PDF parsing | PyMuPDF (fitz) | ≥ 1.27 | Text extraction + rendering |
| DOCX parsing | python-docx | ≥ 1.2 | Paragraph / style extraction |
| LLM | Google Gemini 2.5-Flash | via google-genai ≥ 1.73.1 | Answer generation |
| Config | pydantic-settings | ≥ 2.0 | Environment variable binding |
| Async files | aiofiles | ≥ 24.1 | Non-blocking upload writes |

### Frontend

| Component | Library | Version | Purpose |
|---|---|---|---|
| UI framework | React | 19.2 | Component-based interface |
| Build tool | Vite | 8.0 | HMR dev server + bundle |
| CSS | Tailwind CSS | 4.2 | Utility-first styling |
| Icons | Material Symbols | (CDN) | Icon set |
| Portal | react-dom/createPortal | 19.2 | Snippet modal outside DOM tree |

### Embedding & Reranking Models

| Model | Params | Dimension | Purpose |
|---|---|---|---|
| nomic-ai/nomic-embed-text-v1.5 | ~137M | 768 | Semantic embeddings |
| cross-encoder/ms-marco-MiniLM-L-6-v2 | ~22M | — | Passage relevance logits |

Both models run locally via sentence-transformers, downloaded on first use and cached in the model store.

---

## 4. Data Storage Layer

### 4.1 SQLite Schema

```
Document
  id            INTEGER PK
  filename      TEXT UNIQUE          -- stored as {hash_prefix}_{original_name}
  original_name TEXT                 -- display name
  file_type     TEXT                 -- "pdf" | "docx"
  page_count    INTEGER
  file_hash     TEXT UNIQUE          -- SHA256, duplicate guard
  status        TEXT                 -- pending | processing | indexed | failed
  created_at    DATETIME

Chunk
  id            INTEGER PK
  document_id   INTEGER FK → Document (cascade delete)
  page_number   INTEGER
  passage_index INTEGER              -- 1-based, per-page counter
  section_title TEXT
  text          TEXT
  chroma_id     TEXT UNIQUE          -- UUID linking to ChromaDB

Session
  id            INTEGER PK
  title         TEXT                 -- first 60 chars of first question
  created_at    DATETIME
  updated_at    DATETIME

Message
  id            INTEGER PK
  session_id    INTEGER FK → Session (cascade delete)
  question      TEXT
  answer        TEXT
  sources_json  TEXT                 -- JSON array of CitationSource
  created_at    DATETIME
```

### 4.2 ChromaDB Collection

- **Name**: `document_chunks`
- **Distance metric**: Cosine similarity
- **Persistence**: `./data/chroma` (survives restart)
- **Schema per entry**:
  ```
  id:        chroma_id (UUID)
  embedding: float32[768]
  document:  chunk text
  metadata:  { doc_id, doc_name, page_number, passage_index, section_title }
  ```

---

## 5. Document Ingestion Pipeline

```
Upload (POST /api/documents/upload)
       │
       ▼
  Hash file (SHA256)
  ├─ Duplicate? → 409 Conflict
  └─ New? → save to ./uploads/{hash_prefix}_{original_name}
       │
       ▼
  Insert Document row (status=pending)
  Start background task
       │
       ▼
  ┌─────────────────────────────────────────┐
  │  1. PARSE                               │
  │                                         │
  │  PDF path:                              │
  │    PyMuPDF → blocks with font metrics   │
  │    Heading heuristic:                   │
  │      font_size ≥ 13.0 pt               │
  │      len(text) < 200 chars             │
  │      no trailing period                 │
  │    → list[{page, text, category}]       │
  │                                         │
  │  DOCX path:                             │
  │    python-docx → paragraphs             │
  │    Check para.style.name for "heading"  │
  │    Estimate page from char count        │
  │    (CHARS_PER_PAGE = 2000)              │
  │    → list[{page, text, category}]       │
  └─────────────────────────────────────────┘
       │
       ▼
  ┌─────────────────────────────────────────┐
  │  2. CHUNK                               │
  │                                         │
  │  MAX_CHUNK_CHARS = 1500                 │
  │  OVERLAP_CHARS   = 250                  │
  │  MIN_SECTION_CHARS = 150               │
  │                                         │
  │  Group elements by section heading.     │
  │  When section text > MAX_CHUNK_CHARS:   │
  │    Snap end to last word boundary       │
  │    Create chunk with that text          │
  │    Advance start = end - OVERLAP        │
  │    Snap start forward to next word      │
  │                                         │
  │  Sections < MIN_SECTION_CHARS:          │
  │    Carry forward as prefix for next     │
  │    section (not silently discarded)     │
  │                                         │
  │  Assign passage_index (1-based per page)│
  └─────────────────────────────────────────┘
       │
       ▼
  ┌─────────────────────────────────────────┐
  │  3. EMBED                               │
  │                                         │
  │  Model: nomic-embed-text-v1.5           │
  │  Each chunk prefixed:                   │
  │    "search_document: " + chunk_text     │
  │  normalize_embeddings = True            │
  │  Output: float32[N_chunks × 768]        │
  └─────────────────────────────────────────┘
       │
       ▼
  ┌─────────────────────────────────────────┐
  │  4. STORE                               │
  │                                         │
  │  ChromaDB: embeddings + metadata        │
  │  SQLite:   Chunk rows                   │
  └─────────────────────────────────────────┘
       │
       ▼
  ┌─────────────────────────────────────────┐
  │  5. REBUILD BM25 INDEX                  │
  │                                         │
  │  Fetch all chunks from ChromaDB         │
  │  Tokenize: strip punctuation, lowercase │
  │  Initialize BM25Okapi on full corpus    │
  └─────────────────────────────────────────┘
       │
       ▼
  Mark Document status = "indexed"
```

### Chunking Design Detail

The chunker avoids two common failure modes:

**Mid-word splits**: When the `MAX_CHUNK_CHARS` boundary falls inside a word, the code walks backward to the last whitespace character before the boundary, ensuring chunks always begin and end on word edges.

**Overlap word alignment**: The overlap is applied by subtracting `OVERLAP_CHARS` from the end position, then walking forward past partial words so the new chunk starts on a clean word boundary.

**Small section carry-forward**: A section with less than `MIN_SECTION_CHARS` characters is not flushed as a standalone chunk (which would produce a near-empty retrieval unit). Instead its text is prepended to the next section's accumulation buffer, keeping context together.

---

## 6. The RAG Retrieval System

The retrieval system is the core of the product. It runs a nine-step hybrid pipeline on every query and returns between 1 and 5 chunks.

```
retrieve(query, doc_ids=None)
│
├─ 1. Embed query  (nomic, "search_query: " prefix)
│
├─ 2. Vector search  (ChromaDB, top 15)
│
├─ 3. BM25 search  (in-memory, top 15)
│
├─ 4. Gate 1  (coverage check — fail fast if corpus unrelated)
│
├─ 5. Merge + deduplicate  (by doc_id / page / passage_index)
│
├─ 6. Cross-encoder scoring  (ms-marco, sigmoid probabilities)
│
├─ 7. Fallback  (bypass reranker if max CE prob < 0.10)
│
├─ 8. Combined score  (weighted sum)
│
└─ 9. Dynamic selection  (1–5 chunks by score-ratio cutoff)
```

### 6.1 Embedding & Vector Search

The query is embedded with the **nomic-embed-text-v1.5** model using the `"search_query: "` prefix — the model was trained with asymmetric prefixes: documents use `"search_document: "` and queries use `"search_query: "`, optimising the vector space for retrieval rather than similarity.

ChromaDB performs cosine nearest-neighbour search, returning the top 15 results. Each result carries a score of `1 - cosine_distance`, so higher is more similar.

```python
HYBRID_CANDIDATES = 15
query_vec = embed_query(query)   # "search_query: " + query
vector_results = chroma.query(query_vec, n_results=15, doc_ids=doc_ids)
```

### 6.2 BM25 Keyword Search

BM25 (Best Match 25) is a classical term-frequency/inverse-document-frequency ranking function that captures exact and near-exact keyword matches the vector model may miss (product codes, proper nouns, rare technical terms).

The implementation uses **BM25Okapi** — the Okapi variant which applies a saturation function to term frequency, preventing a single very frequent term from dominating the score.

**Tokenisation** strips punctuation before splitting to avoid treating `"API."` and `"API"` as different tokens:

```python
def _tokenize(text: str) -> list[str]:
    return re.sub(r"[^\w\s]", " ", text).lower().split()
```

The index is in-memory and rebuilt after every ingestion or deletion. Scores are normalised to `[0, 1]` at query time by dividing by the maximum score in the result set.

### 6.3 Hybrid Merge & Deduplication

Chunks from both sources are merged into a single dictionary keyed by their unique identity:

```
key = f"{doc_id}_{page_number}_{passage_index}"
```

A chunk appearing in both vector and BM25 results gets both scores; a chunk from only one source gets `0.0` for the other. This prevents double-counting while giving a genuine boost to chunks that rank highly in both retrieval modes.

```python
merged[key] = {
    **chunk,
    "vector_score": chunk["score"],  # from vector search
    "bm25_score": 0.0                # overwritten if also in BM25
}
```

### 6.4 Gate 1 — Coverage Check

Before incurring cross-encoder cost, a lightweight coverage check rejects queries the corpus clearly cannot answer:

| Condition | Action |
|---|---|
| Zero results from both sources | Return `([], False)` |
| `top_vector_sim < 0.25` AND `bm25_hits == 0` | Return `([], False)` |
| Any other combination | Pass — continue pipeline |

`coverage_ok = False` is the signal for the router to return "not found" without calling Gemini at all, saving latency and quota.

The threshold `0.25` is deliberately permissive — it only blocks genuinely off-topic queries (e.g. asking about cooking recipes when the corpus is a software manual). Everything else is passed to the cross-encoder and ultimately to Gemini's own judgement (Gate 2).

### 6.5 Cross-Encoder Reranking

A **cross-encoder** differs from the embedding model in a fundamental way:

- **Bi-encoder** (what generates embeddings): encodes query and document independently, then compares vectors. Fast, scalable, but the two representations never interact.
- **Cross-encoder**: takes the `[query, document]` pair together as a single input and produces a single relevance score. Slower, but far more accurate because the model can attend to exact token overlaps, negations, and entity references.

The model used is **ms-marco-MiniLM-L-6-v2**, a 22M-parameter distilled model trained on the MS-MARCO passage ranking dataset. It outputs raw logits (unbounded real numbers).

```python
pairs = [[query, chunk["text"]] for chunk in candidates]
raw_scores = reranker.predict(pairs)
```

Logits are converted to `[0, 1]` probabilities via sigmoid with numerical clipping to prevent overflow:

```python
def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-500.0, min(500.0, x))))
```

**Fallback**: If the maximum CE probability across all candidates is below `0.10`, the reranker is considered confused (this happens when a query is syntactically valid but semantically far from all passages). In this case all `ce_prob` values are zeroed out, and the combined score degrades gracefully to pure hybrid retrieval order.

```python
if max_ce_prob < FALLBACK_CE_PROB_MIN:
    for chunk in candidates:
        chunk["ce_prob"] = 0.0
```

### 6.6 Combined Scoring

The final score is a weighted linear combination of the three signals:

```
final_score = 0.5 × vector_score
            + 0.3 × bm25_norm_score
            + 0.2 × ce_sigmoid_prob
```

| Weight | Signal | Rationale |
|---|---|---|
| 0.5 | Vector similarity | Primary semantic relevance signal |
| 0.3 | BM25 normalised | Lexical overlap; important for named entities and codes |
| 0.2 | Cross-encoder prob | Precise re-ranking; soft boost not a hard gate |

The CE weight is intentionally the smallest because:
1. It is the most expensive to compute.
2. It should adjust rankings rather than override them.
3. The fallback zeroes it out anyway when unreliable.

Chunks are sorted descending by `final_score`.

### 6.7 Dynamic Chunk Selection

Earlier versions passed a fixed five chunks to Gemini regardless of score distribution. This wastes context when only one passage is genuinely relevant (the LLM sees four low-quality passages that may introduce confabulation).

The current approach uses a **score-ratio cutoff**: a chunk is included only if its score is at least 50% of the top chunk's score.

```python
MAX_CHUNKS_TO_LLM = 5
SCORE_RATIO_CUTOFF = 0.5

top_score = ranked[0]["final_score"]
top: list[dict] = []

for chunk in ranked:
    if len(top) >= MAX_CHUNKS_TO_LLM:
        break
    if len(top) == 0 or chunk["final_score"] >= top_score * SCORE_RATIO_CUTOFF:
        top.append(chunk)
    else:
        break  # score dropped below ratio — stop
```

This produces natural behaviour across score distributions:

| Score distribution | Threshold | Result |
|---|---|---|
| `[0.80, 0.70, 0.60, 0.50, 0.40]` | 0.40 | All 5 pass (gradual decline = all relevant) |
| `[0.80, 0.20, 0.18, 0.15, 0.12]` | 0.40 | Only 1 (clear winner + noise) |
| `[0.80, 0.75, 0.72, 0.30, 0.28]` | 0.40 | 3 chunks (natural gap in relevance) |

Edge case: if `top_score = 0`, the threshold is `0 × 0.5 = 0`, so all chunks pass and `MAX_CHUNKS_TO_LLM` acts as the cap — safe fallback.

---

## 7. Answer Generation

### 7.1 Context Building

Retrieved chunks are serialised into a structured prompt block:

```
DOCUMENT PASSAGES:

[Passage 1]
Document: annual_report_2024.pdf
Page: 12 | Passage: 3
Section: Financial Highlights
---
Revenue for FY2024 was $4.2 billion...

[Passage 2]
...

QUESTION: What was the revenue growth in FY2024?
```

Conversation history (max 5 prior turns) is prepended with an explicit instruction that it is context-only and must not be used as a factual source.

### 7.2 Gemini Instruction

The system prompt strictly enforces document grounding:

- Answer only from the provided passages.
- If the answer is not in the passages, set `found: false`.
- Each `sources` entry must include `doc_name`, `page`, `passage_index`, `section_title`, and the exact `text` of the cited passage.
- Temperature is set to `0.0` for reproducible, factual responses.

### 7.3 Source Text Restoration

Gemini often paraphrases the `text` field in its JSON output even though it is instructed to return it verbatim. This breaks the snippet highlighter which needs to search for the exact original text in the PDF.

The query router performs a restoration step after generation:

```python
_chunk_text_by_key = {
    (c["metadata"]["doc_name"], c["metadata"]["page_number"],
     c["metadata"]["passage_index"]): c["text"]
    for c in chunks
}
for src in result.get("sources", []):
    key = (src.get("doc_name"), src.get("page"), src.get("passage_index"))
    if key in _chunk_text_by_key:
        src["text"] = _chunk_text_by_key[key]  # overwrite with original
```

This ensures the text stored in the database and returned to the frontend is always the verbatim indexed chunk — matching what physically exists in the PDF.

---

## 8. Snippet Rendering & Highlighting

When a user clicks a citation pill, the backend renders the exact PDF page as a PNG with the cited passage highlighted in yellow.

### 8.1 Architecture

```
GET /api/snippets/render
  ?doc_name=report.pdf
  &page=12
  &text=Revenue for FY2024...
  &passage_index=3
        │
        ▼
  Look up Document in SQLite by original_name
  ├─ Not found → 404
  ├─ file_type == "docx" → 501 (text excerpt shown instead)
  └─ PDF found → get file path
        │
        ▼
  If passage_index provided:
    Fetch exact chunk text from SQLite
    Use that as search text (original, not LLM-rewritten)
        │
        ▼
  snippet.render_snippet(pdf_path, page, text)
        │
        ▼
  Return PNG bytes
  Cache-Control: max-age=3600
```

### 8.2 Text Search on a PDF Page

The central challenge is locating a text passage inside a PDF page's word list. PDFs do not store text as plain strings — they store glyph streams, and text is reconstructed by the PDF reader. This introduces several obstacles:

**Ligatures**: PDFs often encode `fi`, `fl`, `ff` as single ligature glyphs (`ﬁ`, `ﬂ`, `ﬀ`, etc.). The indexed text was extracted by PyMuPDF and has these expanded, but the word-level search API may see them as ligatures. Normalisation expands all ligatures before any comparison.

**Soft hyphens**: End-of-line hyphens (`U+00AD`) appear in extracted text and must be stripped.

**Whitespace**: Multiple consecutive spaces, tabs, and newlines are collapsed to single spaces.

**Text normalisation**:
```python
_LIGATURES = {
    "\ufb00": "ff",   "\ufb01": "fi",   "\ufb02": "fl",
    "\ufb03": "ffi",  "\ufb04": "ffl",  "\ufb05": "st",  "\ufb06": "st",
}

def _norm(text: str) -> str:
    for lig, rep in _LIGATURES.items():
        text = text.replace(lig, rep)
    text = text.replace("\u00ad", "")          # soft hyphen
    return re.sub(r"\s+", " ", text).strip()
```

### 8.3 Start and End Anchor Search

Instead of searching for the entire passage (which may span pages and be unreliable), the system identifies **start** and **end anchors** — short, reliable phrases extracted from the passage boundaries.

**Start anchor extraction**:

```python
_SEARCH_WORDS = 6
_WORD_OFFSETS = (0, 1, 2, 3, 5, 10)
_MIN_WORD_LEN = 2
_MIN_PHRASE_LEN = 12
```

Words are extracted starting from offset 0. If the resulting phrase is below `_MIN_PHRASE_LEN` characters or consists of very short words, the search retries with the next word offset. This handles cases where a chunk begins with a page number, bullet symbol, or short fragment from the previous chunk's overlap.

**Page drift correction**: PDF page numbers in metadata may be off by ±1 or ±2 pages due to cover pages, roman numerals, or index pages. The system searches within a window of ±2 pages:

```python
PAGE_SEARCH_WINDOW = (-2, -1, 0, 1, 2)

for page_offset in PAGE_SEARCH_WINDOW:
    candidate_page = target_page + page_offset
    result = _find_phrase_on_page(doc, candidate_page, phrase)
    if result:
        break
```

### 8.4 Y-Band Highlighting

Once start and end anchors are located, their Y-coordinates define a horizontal band on the page. All PDF words whose bounding box falls within this band are collected and highlighted.

```
Page coordinate space (Y increases downward):

 ┌────────────────────────────┐
 │                            │  ← y_start (top of first anchor word)
 │  Revenue for FY2024 was    │  ◄─── highlighted band
 │  $4.2 billion, representing│
 │  a 23% increase over       │
 │  the prior year period.    │  ← y_end (bottom of last anchor word)
 │                            │
 └────────────────────────────┘
```

```python
# Collect all words between start_y and end_y
band_words = [
    w for w in page.get_text("words")
    if w[1] >= start_y - TOLERANCE and w[3] <= end_y + TOLERANCE
]
```

**End anchor estimation**: If the end phrase cannot be found on the page (the passage spans a page break), the system estimates `end_y` from the passage character count and the median line height on the page:

```python
_CHARS_PER_LINE = 80  # characters per text line estimate

estimated_lines = len(passage_text) / _CHARS_PER_LINE
end_y = start_y + (estimated_lines * median_line_height)
```

### 8.5 Multi-Column Detection

Many PDF documents use two-column layouts. If the highlight band is applied naively, it may capture words from both columns even though the passage is in only one.

The system detects multi-column layout by checking whether any word in the band crosses the horizontal page centre:

```python
page_cx = page.rect.width / 2
is_single_column = any(
    w[0] < page_cx - _COL_X_MARGIN and w[2] > page_cx + _COL_X_MARGIN
    for w in band_words
)
```

- If any word crosses the centre: **single-column** — no filtering applied.
- If no word crosses: **multi-column** — words are constrained to the column containing the start anchor (left half or right half of the page).

### 8.6 Rendering

PyMuPDF draws a yellow `Highlight` annotation over each word's bounding rectangle, then renders the page to a PNG at 1.5× resolution for readability:

```python
for word in highlight_words:
    rect = fitz.Rect(word[0], word[1], word[2], word[3])
    annot = page.add_highlight_annot(rect)
    annot.update()

mat = fitz.Matrix(1.5, 1.5)
pix = page.get_pixmap(matrix=mat)
return pix.tobytes("png")
```

### 8.7 Caching

Rendered snippets are expensive (~500ms–2s). An LRU cache keyed on `(pdf_path, page, text)` stores up to 50 entries (~2.75 MB):

```python
@lru_cache(maxsize=50)
def _render_cached(pdf_path: str, page: int, text: str) -> bytes: ...
```

The cache is invalidated when a document is deleted.

---

## 9. Streaming Architecture

### 9.1 Server-Sent Events (SSE)

The streaming endpoint uses SSE — a one-way HTTP persistent connection where the server pushes newline-delimited JSON events:

```
POST /api/query/stream
  Content-Type: application/json

Response:
  Content-Type: text/event-stream

data: {"type": "token", "text": "Revenue "}
data: {"type": "token", "text": "for FY2024 "}
data: {"type": "token", "text": "was $4.2 billion."}
data: {"type": "done", "found": true, "answer": "...", "sources": [...], "session_id": 7}
```

### 9.2 NOT_FOUND Sentinel

Gemini in streaming mode cannot return structured JSON (streaming and `response_mime_type="application/json"` are mutually exclusive). Instead, the system prompt instructs Gemini to output the literal string `NOT_FOUND` if it cannot answer from the passages.

To detect this sentinel without mistakenly cutting it from a valid answer, the router buffers the last 8 characters of the stream. On each incoming chunk, only the "safe" portion (everything except the buffer) is forwarded to the client. At stream end, the full buffer is checked:

```python
SENTINEL = "NOT_FOUND"
HOLD_BACK = len(SENTINEL)  # = 8

buffer = ""
for chunk in gemini_stream:
    buffer += chunk
    safe = buffer[:-HOLD_BACK]
    if safe:
        yield token_event(safe)
    buffer = buffer[-HOLD_BACK:]

# Stream ended — inspect buffer
if SENTINEL in buffer:
    found = False
    # Do NOT yield the sentinel to the client
else:
    found = True
    if buffer:
        yield token_event(buffer)
```

### 9.3 Gate 1 in Streaming Mode

The retrieval gate check runs before the SSE stream opens. If Gate 1 fails (no coverage), the endpoint returns a single `"done"` event with `found=false` immediately — no Gemini call is made:

```
data: {"type": "done", "found": false, "answer": "", "sources": [], "session_id": null}
```

---

## 10. Frontend Architecture

### 10.1 Component Tree

```
App
├─ ChatSidebar
│   ├─ Logo
│   ├─ New Chat button
│   ├─ Navigation (Chat / Upload / Settings)
│   ├─ Session list (max 10, with delete on hover)
│   └─ Status indicator
│
└─ view === "chat"  → ChatInterface
   view === "upload" → Upload + DocumentLibrary
   view === "settings" → Placeholder
```

### 10.2 Streaming Message Handling

```javascript
const res = await fetch("/api/query/stream", { method: "POST", body: JSON.stringify(payload) })
const reader = res.body.getReader()

// Insert empty streaming bubble
setMessages(prev => [...prev, { type: "ai", text: "", streaming: true }])

let buffer = ""
while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value)
    const lines = buffer.split("\n")
    buffer = lines.pop()  // keep incomplete line in buffer

    for (const line of lines) {
        if (!line.startsWith("data: ")) continue
        const event = JSON.parse(line.slice(6))

        if (event.type === "token") {
            // Append token to streaming bubble
            setMessages(prev => prev.map((m, i) =>
                i === prev.length - 1 ? { ...m, text: m.text + event.text } : m
            ))
        } else if (event.type === "done") {
            // Finalise message with sources
            setMessages(prev => prev.map((m, i) =>
                i === prev.length - 1
                    ? { ...m, streaming: false, found: event.found, sources: event.sources }
                    : m
            ))
        }
    }
}
```

### 10.3 Thinking Phase Animation

While the streaming bubble exists but has no text yet (waiting for first token), four cycling states are shown with icons and animated dots:

```javascript
const THINKING_PHASES = [
  { label: "Thinking",            icon: "psychology"    },
  { label: "Searching documents", icon: "manage_search" },
  { label: "Analyzing",           icon: "analytics"     },
  { label: "Preparing answer",    icon: "edit_note"     },
]
// Phase advances every 1600ms via setInterval
```

### 10.4 Snippet Modal

Clicking a citation pill opens a full-screen modal (via `createPortal` to `document.body`, ensuring correct z-index stacking regardless of parent DOM context):

```
┌─────────────────────────────────────────────────────┐
│ report_2024.pdf   Page 12 · Passage 3    [Copy] [✕] │
├─────────────────────────────────────────────────────┤
│                                                     │
│  [PDF page rendered at 1.5× with yellow highlight]  │
│                                                     │
├─────────────────────────────────────────────────────┤
│ Cited: "Revenue for FY2024 was $4.2 billion..."     │
└─────────────────────────────────────────────────────┘
```

States:
- **Loading**: spinner animation
- **DOCX**: text excerpt with note that page rendering is PDF-only
- **Error**: error icon + message
- **Success**: PNG image

The Copy Image button writes the PNG to the clipboard using the Clipboard API (fallback: trigger a download).

---

## 11. API Reference

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/documents/upload` | Upload PDF or DOCX |
| `GET` | `/api/documents` | List all documents |
| `GET` | `/api/documents/{id}/status` | Document metadata |
| `GET` | `/api/documents/{id}/progress` | SSE ingestion progress |
| `DELETE` | `/api/documents/{id}` | Delete document + chunks |
| `POST` | `/api/query` | Non-streaming Q&A (JSON) |
| `POST` | `/api/query/stream` | Streaming Q&A (SSE) |
| `GET` | `/api/sessions` | List all sessions |
| `GET` | `/api/sessions/{id}` | Session + messages |
| `DELETE` | `/api/sessions/{id}` | Delete session |
| `GET` | `/api/snippets/render` | Render PDF snippet as PNG |

---

## 12. End-to-End Flow

### Upload Flow

```
User drops PDF
  → POST /api/documents/upload
  → Hash check (SHA256)
  → Save file to ./uploads
  → Insert Document (status=pending)
  → Background ingestion starts
      → Parse → Chunk → Embed → Store → Rebuild BM25
  → SSE /api/documents/{id}/progress streams stages to UI
  → Frontend polls document list, shows "indexed" badge
```

### Query Flow

```
User types question, hits Enter
  → POST /api/query/stream
  → embed_query(question)
  → vector_search(query_vec, top 15)
  → bm25_search(question, top 15)
  → Gate 1 check
  → merge + deduplicate
  → cross_encoder_score(query, candidates)
  → combined_score = 0.5v + 0.3b + 0.2c
  → dynamic_select (score ratio 0.5)
  → load_history(session_id, max 5 turns)
  → stream Gemini 2.5-Flash
  → buffer NOT_FOUND detection
  → SSE token events → frontend appends tokens
  → SSE done event → frontend shows citation pills
  → save Message to SQLite
```

### Snippet Flow

```
User clicks citation pill
  → GET /api/snippets/render?doc_name=...&page=...&passage_index=...
  → lookup Document in SQLite
  → fetch exact chunk text from Chunk table (if passage_index given)
  → open PDF with PyMuPDF
  → normalise text (ligatures, soft hyphens, whitespace)
  → extract start anchor phrase (with word offsets)
  → search page ± 2 (page drift window)
  → extract end anchor phrase
  → compute y-band (start_y → end_y)
  → detect single/multi-column
  → collect words in band (column-constrained if needed)
  → add yellow Highlight annotations
  → render page at 1.5× → PNG bytes
  → LRU cache (maxsize=50)
  → return PNG, Cache-Control: max-age=3600
  → frontend displays in modal
```

---

## 13. Performance Characteristics

### Query Latency Breakdown

| Stage | Typical Duration |
|---|---|
| Query embedding (nomic) | 20–50ms |
| ChromaDB vector search (top 15) | 10–50ms |
| BM25 search (in-memory, full corpus) | < 1ms |
| Cross-encoder reranking (15–30 pairs) | 80–200ms |
| Gemini first token (streaming) | 500ms–1.5s |
| Gemini full response | 1–4s |
| **Total to first token** | **~700ms–1.8s** |

### Ingestion Throughput

| Stage | Typical Rate |
|---|---|
| PDF parsing (PyMuPDF) | ~5–20 pages/sec |
| Embedding (nomic, CPU) | ~100–200 chunks/sec |
| ChromaDB insert | ~500 chunks/sec |

### Memory Footprint

| Component | Memory |
|---|---|
| nomic-embed-text-v1.5 model | ~550MB |
| ms-marco-MiniLM-L-6-v2 model | ~85MB |
| ChromaDB (10k chunks, in-process) | ~200MB |
| BM25 index (10k chunks) | ~50MB |
| Snippet LRU cache (50 entries) | ~2.75MB |

---

## 14. Configuration & Environment

### Environment Variables (`.env`)

```bash
GEMINI_API_KEY=AIza...         # required
DATABASE_URL=sqlite:///./data/app.db     # optional, default shown
CHROMA_PATH=./data/chroma                # optional, default shown
UPLOAD_DIR=./uploads                     # optional, default shown
```

### Directory Layout

```
Document-RAG/
├── backend/
│   ├── main.py                  # FastAPI app, lifespan, routers
│   ├── config.py                # pydantic-settings config
│   ├── database.py              # SQLAlchemy engine + session
│   ├── models.py                # ORM models (Document, Chunk, Session, Message)
│   ├── routers/
│   │   ├── documents.py         # upload, progress SSE, list, delete
│   │   ├── query.py             # non-stream + stream Q&A
│   │   ├── sessions.py          # session + message history
│   │   └── snippets.py          # PDF snippet rendering
│   ├── services/
│   │   ├── ingestion.py         # parse → chunk → embed → store
│   │   ├── retrieval.py         # hybrid retrieval pipeline
│   │   ├── generation.py        # Gemini prompt + streaming
│   │   ├── embeddings.py        # nomic embed_query / embed_documents
│   │   ├── vectorstore.py       # ChromaDB wrapper
│   │   ├── bm25_index.py        # BM25Okapi in-memory index
│   │   └── snippet.py           # PDF page rendering + highlighting
│   └── tests/
│       ├── test_generation.py
│       ├── test_ingestion.py
│       ├── test_query.py
│       └── test_snippets.py
├── frontend/
│   ├── src/
│   │   ├── App.jsx              # root, state, layout
│   │   ├── components/
│   │   │   ├── ChatInterface.jsx
│   │   │   └── ChatSidebar.jsx
│   │   └── index.css            # global styles, scrollbar, animations
│   ├── package.json
│   └── vite.config.js
├── data/                        # created at runtime
│   ├── app.db                   # SQLite
│   └── chroma/                  # ChromaDB persistence
├── uploads/                     # created at runtime
├── pyproject.toml
└── .env
```

### Running Locally

```bash
# Backend
uv sync
uv run uvicorn backend.main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend
npm install
npm run dev
```

The frontend dev server runs on `http://localhost:5173` and proxies `/api` requests to `http://localhost:8000`.
