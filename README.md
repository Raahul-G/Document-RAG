# Document RAG

A locally hosted Retrieval-Augmented Generation (RAG) system for querying PDF and DOCX documents using hybrid search, cross-encoder reranking, and streaming LLM responses. Two branches are available: one powered by **Gemini 2.5 Flash** (requires an API key) and one running a **fully local Phi-4-mini LLM** with no external dependencies.

---

## Branches

| Branch | LLM | API Key Required | Fully Offline |
|--------|-----|-----------------|---------------|
| `main` | Gemini 2.5 Flash (Google) | Yes — Google AI Studio | No |
| `localllm` | Phi-4-mini Q4_K_M (local GGUF) | No | Yes |

Both branches share the same retrieval pipeline (embeddings, BM25, cross-encoder reranking) and frontend. Only the generation layer differs.

```bash
git checkout main       # Gemini version
git checkout localllm   # fully local version
```

---

## Screenshots

**Home — empty state**
![Home screen showing the chat interface ready for queries](docs/screenshots/01-home.png)

**Knowledge Ingestion — document library**
![Upload page with drag-and-drop area, indexed document, and 100% index coverage](docs/screenshots/02-upload.png)

**Chat — streaming answers with source citations**
![Chat interface showing a multi-turn conversation with cited passages](docs/screenshots/03-chat.png)

**Snippet Viewer — exact passage highlight**
![Snippet viewer modal showing the retrieved passage highlighted in the source document](docs/screenshots/04-snippet-viewer.png)

---

## Architecture Overview

```
Upload (PDF/DOCX)
       │
       ▼
┌─────────────────────────────────────────┐
│              Ingestion Pipeline          │
│  Parse → Chunk → Embed → Store          │
└────────────┬──────────────┬─────────────┘
             │              │
             ▼              ▼
       ChromaDB          SQLite
    (vector store)    (chunk metadata
                       + sessions)
             │              │
             └──────┬───────┘
                    │
             ┌──────▼───────┐
             │  BM25 Index  │ (pickle-persisted, loaded from disk or rebuilt)
             └──────┬───────┘
                    │
             User Query
                    │
                    ▼
        ┌───────────────────────┐
        │  Query Rewriting      │
        │  (anaphora resolution │
        │   using history)      │
        └───────────┬───────────┘
                    │
                    ▼
        ┌───────────────────────┐
        │  Hybrid Retrieval     │
        │  Vector (top 15)      │
        │  + BM25 (top 15)      │
        │  → Merge & Dedupe     │
        └───────────┬───────────┘
                    │
                    ▼
        ┌───────────────────────┐
        │  Cross-Encoder        │
        │  Reranking            │
        │  ms-marco-MiniLM-L-6  │
        └───────────┬───────────┘
                    │
                    ▼
        ┌───────────────────────┐
        │  main:   Gemini 2.5   │
        │  localllm: Phi-4-mini │
        │  (streaming / JSON)   │
        └───────────────────────┘
```

---

## Retrieval Pipeline

### 1. Document Ingestion

**Supported formats:** PDF (via OpenDataLoader PDF), DOCX (via python-docx)

**PDF parsing** uses OpenDataLoader PDF (Java-based, CPU-only) which produces a structured JSON element tree from each PDF. Headings are identified from the PDF's structural tags (`heading_level` ≤ 6 → Title; deeper levels → NarrativeText) — no font-size heuristics. Tables are flattened row-by-row as `col1 | col2 | col3` and kept as a single semantic unit. Lists are extracted per item. Multi-column reading order is handled automatically via XY-Cut++. Scanned PDFs are supported via built-in OCR (80+ languages). PyTorch is not required.

PyMuPDF is still used by the snippet viewer to **render** PDF pages as PNG images — it is not involved in text extraction.

**DOCX parsing** reads paragraph styles directly. Paragraphs with a style name containing `heading` or `title` are treated as section boundaries. Page numbers are estimated from character count (~2,000 chars per page) since Word does not expose real page breaks programmatically.

**Deduplication:** Files are SHA-256 hashed at upload time. Re-uploading an identical file returns HTTP 409.

---

### 2. Chunking Strategy

| Parameter | Value |
|-----------|-------|
| Max chunk size | 1,000 characters |
| Overlap | 150 characters (~15%) |
| Min section size | 150 characters (merged upward if smaller) |

Chunking is **section-aware**: the parser first segments the document into headed sections, then splits oversized sections at word boundaries with the configured overlap. Sub-threshold sections (< 150 chars) are carried forward and prepended to the next section rather than silently discarded.

Each chunk is assigned a `passage_index` (sequential counter per page) which the frontend uses to render precise in-document highlights via the snippet viewer.

---

### 3. Embedding Model — `nomic-ai/nomic-embed-text-v1.5`

| Property | Value |
|----------|-------|
| Dimensions | 768 |
| Parameters | ~137M |
| Runtime | FastEmbed ONNX (int8-quantized) |
| PyTorch required | No |
| Runs locally | Yes — CPU |

Nomic Embed v1.5 requires **task prefixes** (it was trained with them — omitting lowers recall):

```
Indexing:  "search_document: {chunk_text}"
Query:     "search_query: {query_text}"
```

FastEmbed downloads the ONNX int8-quantized model at first use and caches it under `~/.cache/fastembed`. In the Docker image, both the embedding model and the reranker are downloaded at build time so the container starts without any download delay.

---

### 4. Vector Store — ChromaDB

| Property | Value |
|----------|-------|
| Distance metric | Cosine (`hnsw:space: cosine`) |
| Index type | HNSW (Hierarchical Navigable Small World) |
| Persistence | SQLite-backed, in-process |
| Metadata per chunk | `doc_id`, `doc_name`, `page_number`, `passage_index`, `section_title` |

ChromaDB runs embedded inside the FastAPI process — no separate container or network call.

**Startup migration guard:** On startup, the server probes the stored vector dimension. If it detects a mismatch (e.g. 384-dim vectors from a previous `all-MiniLM-L6-v2` setup instead of the expected 768-dim), it automatically clears the ChromaDB collection, the SQLite chunk table, and the BM25 pickle before loading proceeds. This prevents silent score degradation from stale embeddings.

---

### 5. BM25 Hybrid Search

| Property | Value |
|----------|-------|
| Library | `rank-bm25` (BM25Okapi variant) |
| Persistence | Pickle file (`BM25_PKL_PATH`, default `data/bm25.pkl`) |
| Startup | Loads from disk in ~50ms; rebuilds from ChromaDB only if pickle is missing or invalid |
| Tokenisation | Regex — strips punctuation, lowercases |

BM25 excels at exact keyword matches where dense vectors underperform — acronyms, proper nouns, version numbers, and rare technical terms. After each document ingestion, the index is fully rebuilt (BM25Okapi does not support incremental updates) and re-persisted to disk.

---

### 6. Cross-Encoder Reranking — `Xenova/ms-marco-MiniLM-L-6-v2`

| Property | Value |
|----------|-------|
| Parameters | ~22M |
| Runtime | FastEmbed ONNX (via `fastembed.rerank.cross_encoder.TextCrossEncoder`) |
| PyTorch required | No |
| Input | (query, passage) pair |
| Output | Raw relevance logit → sigmoid probability |
| Runs locally | Yes — CPU |

The ONNX export (`Xenova/ms-marco-MiniLM-L-6-v2`) uses the same weights as `cross-encoder/ms-marco-MiniLM-L-6-v2` — different runtime, zero precision loss.

**Final scoring:**

```
final_score = 0.5 × vector_similarity
            + 0.3 × normalised_bm25
            + 0.2 × cross_encoder_probability
```

**Fallback:** If all cross-encoder probabilities are below 0.15, the reranker is bypassed entirely and raw hybrid retrieval order is used (prevents noisy reranking on out-of-domain queries).

**Dynamic chunk selection:** Chunks scoring ≥ 50% of the top chunk's score are included, up to a hard cap of 5 chunks.

**Gate 1 (coverage check):** If the top vector similarity is below 0.35 and BM25 returns zero hits, the query is rejected before reaching the LLM with `found: false`. This fires only when the corpus genuinely has no relevant content for the question.

---

### 7. LLM

#### `main` — Gemini 2.5 Flash

| Property | Value |
|----------|-------|
| Model | `gemini-2.5-flash` |
| Provider | Google (via `google-genai` SDK) |
| Temperature | 0.0 |
| Max output tokens | 2,048 |
| Requires API key | Yes |

503 overload responses are retried up to 3 times with exponential backoff (1s → 2s → 4s).

#### `localllm` — Phi-4-mini Q4_K_M

| Property | Value |
|----------|-------|
| Model | `microsoft_Phi-4-mini-instruct-Q4_K_M.gguf` |
| Runtime | llama-cpp-python (embedded in FastAPI process) |
| Parameters | 3.8B |
| File size | ~2.5 GB |
| RAM required | ~3.5 GB (model) + ~1 GB (app) |
| Context window | 8,192 tokens (configurable via `LLM_N_CTX`) |
| Requires API key | No |
| Fully offline | Yes |

The model is warmed up at server startup so the first query has no cold-start delay. Non-streaming path uses grammar-constrained JSON decoding (`LlamaGrammar`) to guarantee valid structured output. Streaming path uses a `NOT_FOUND` sentinel approach.

---

## Features

### Multi-Turn Query Rewriting (`localllm` branch)

Before retrieval, the system rewrites anaphoric follow-up questions into self-contained queries using the conversation history. For example:

> Turn 1: "What are the revenue figures for France?"
> Turn 2: "What about Germany?" → rewritten to "What are the revenue figures for Germany?"

The rewritten query is used for retrieval only — the original question is always passed to the LLM for answer generation.

### @Mention Document Scoping

Type `@` in the chat input to scope retrieval to specific documents. Multiple documents can be pinned simultaneously. Selected document IDs are passed as a filter to both the vector search and BM25 search.

### Snippet Viewer

Every source citation opens the exact passage highlighted in the original PDF page rendered as a PNG at 1.5× resolution.

### Streaming Responses

Responses stream token-by-token via Server-Sent Events. The frontend renders tokens progressively as they arrive.

---

## Stack

| Layer | `main` | `localllm` |
|-------|--------|------------|
| Backend | FastAPI + Uvicorn | FastAPI + Uvicorn |
| Database | SQLite (SQLAlchemy) | SQLite (SQLAlchemy) |
| Vector store | ChromaDB (embedded) | ChromaDB (embedded) |
| Embeddings | nomic-embed-text-v1.5 (FastEmbed ONNX) | nomic-embed-text-v1.5 (FastEmbed ONNX) |
| BM25 | rank-bm25 (Okapi) | rank-bm25 (Okapi) |
| Reranker | Xenova/ms-marco-MiniLM-L-6-v2 (FastEmbed ONNX) | Xenova/ms-marco-MiniLM-L-6-v2 (FastEmbed ONNX) |
| LLM | Gemini 2.5 Flash | Phi-4-mini Q4_K_M (llama-cpp-python) |
| PDF parsing (text) | PyMuPDF | OpenDataLoader PDF (Java, CPU) |
| PDF rendering (snippets) | PyMuPDF | PyMuPDF |
| DOCX parsing | python-docx | python-docx |
| PyTorch | Not required | Not required |
| Frontend | React 19 + Vite 6 + Tailwind CSS 4 | React 19 + Vite 6 + Tailwind CSS 4 |
| Packaging | Docker (multi-stage), uv | Docker (multi-stage), uv |

---

## Running with Docker

### `main` branch — Gemini

**Prerequisites:** Docker Desktop, [Google AI Studio](https://aistudio.google.com) API key

```bash
git checkout main
cp .env.example .env
# Set GEMINI_API_KEY in .env

docker compose up --build
```

Open **http://localhost:8000**.

---

### `localllm` branch — Fully Local

**Prerequisites:** Docker Desktop, ~5 GB RAM, ~2.5 GB disk for the model

```bash
git checkout localllm

# Download the model once
pip install huggingface_hub
huggingface-cli download bartowski/microsoft_Phi-4-mini-instruct-GGUF \
  --include "microsoft_Phi-4-mini-instruct-Q4_K_M.gguf" \
  --local-dir ./models/

docker compose up --build
```

Open **http://localhost:8000**. The model loads on startup (~10–20s on CPU), and a loading screen is shown until it is ready.

The first `docker compose build` downloads the FastEmbed embedding model (~270 MB) and the ONNX reranker (~23 MB) into the image layer via BuildKit cache mounts, so subsequent builds skip these downloads even if the layer is invalidated.

---

### Docker Volumes

| Volume | Contents |
|--------|----------|
| `app_data` | SQLite database, ChromaDB index, BM25 pickle |
| `app_uploads` | Uploaded PDF/DOCX files |
| `models_data` | GGUF model file (`localllm` only) |

Data persists across container restarts. To wipe everything:

```bash
docker compose down -v
```

---

## Local Development

**Prerequisites:** Python 3.12, Node 20, [uv](https://docs.astral.sh/uv/)

### `main` branch — Gemini

```bash
git checkout main
uv sync
cp .env.example .env   # set GEMINI_API_KEY

# Backend
uv run uvicorn backend.main:app --reload

# Frontend (separate terminal)
cd frontend && npm install && npm run dev
```

### `localllm` branch — Fully Local

```bash
git checkout localllm
uv sync

# Download model once (can be stored anywhere)
uv run huggingface-cli download bartowski/microsoft_Phi-4-mini-instruct-GGUF \
  --include "microsoft_Phi-4-mini-instruct-Q4_K_M.gguf" \
  --local-dir ./models/

cp .env.example .env
# Set LLM_MODEL_PATH in .env to the full path of the .gguf file

# Backend
uv run uvicorn backend.main:app --reload

# Frontend (separate terminal)
cd frontend && npm install && npm run dev
```

Backend: **http://localhost:8000** — Frontend dev server: **http://localhost:5173**

---

## Environment Variables

### `main` branch

| Variable | Default | Description |
|----------|---------|-------------|
| `GEMINI_API_KEY` | — | Required. Google AI Studio key |
| `DATABASE_URL` | `sqlite:///./data/app.db` | SQLAlchemy connection string |
| `CHROMA_PATH` | `./data/chroma` | ChromaDB persistence directory |
| `UPLOAD_DIR` | `./uploads` | Uploaded file storage |
| `CORS_ORIGINS` | `http://localhost:5173` | Comma-separated allowed origins, or `*` |

### `localllm` branch

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_MODEL_PATH` | `./models/microsoft_Phi-4-mini-instruct-Q4_K_M.gguf` | Path to GGUF model file |
| `LLM_N_CTX` | `8192` | Context window (tokens) |
| `LLM_N_THREADS` | `4` | CPU threads for inference |
| `LLM_N_GPU_LAYERS` | `0` | `0` = CPU only, `-1` = all layers on GPU |
| `LLM_TEMPERATURE` | `0.0` | Sampling temperature |
| `LLM_MAX_TOKENS` | `2048` | Maximum tokens per response |
| `BM25_PKL_PATH` | `data/bm25.pkl` | Path for BM25 pickle persistence |
| `DATABASE_URL` | `sqlite:///./data/app.db` | SQLAlchemy connection string |
| `CHROMA_PATH` | `./data/chroma` | ChromaDB persistence directory |
| `UPLOAD_DIR` | `./uploads` | Uploaded file storage |
| `CORS_ORIGINS` | `http://localhost:5173` | Comma-separated allowed origins, or `*` |
