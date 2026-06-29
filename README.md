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
             │  BM25 Index  │ (in-memory, rebuilt on startup)
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

**Supported formats:** PDF (via PyMuPDF), DOCX (via python-docx)

**PDF parsing** uses PyMuPDF's block-level extraction with font metadata. Spans with font size ≥ 13pt, length < 200 characters, and no trailing period are classified as section headings. This preserves document structure without relying on heuristics like bold detection.

**DOCX parsing** reads paragraph styles directly. Paragraphs with a style name containing `heading` or `title` are treated as section boundaries.

**Deduplication:** Files are SHA-256 hashed at upload time. Re-uploading an identical file returns HTTP 409.

---

### 2. Chunking Strategy

| Parameter | Value |
|-----------|-------|
| Max chunk size | 1,500 characters |
| Overlap | 250 characters (~17%) |
| Min section size | 150 characters (merged upward if smaller) |

Chunking is **section-aware**: the parser first segments the document into headed sections, then splits oversized sections at word boundaries with the configured overlap. This avoids breaking sentences mid-word and keeps semantically related content together.

Each chunk is assigned a `passage_index` within its page, which the frontend uses to render precise in-document highlights via the snippet viewer.

---

### 3. Embedding Model — `nomic-ai/nomic-embed-text-v1.5`

| Property | Value |
|----------|-------|
| Dimensions | 768 |
| Parameters | ~137M |
| Provider | Hugging Face (sentence-transformers) |
| Runs locally | Yes — CPU/GPU |

Nomic Embed v1.5 uses **instruction prefixes** to distinguish indexing from retrieval:

```
Indexing:  "search_document: {chunk_text}"
Query:     "search_query: {query_text}"
```

All embeddings are L2-normalised before storage, making dot product equivalent to cosine similarity.

---

### 4. Vector Store — ChromaDB

| Property | Value |
|----------|-------|
| Distance metric | Cosine (`hnsw:space: cosine`) |
| Index type | HNSW (Hierarchical Navigable Small World) |
| Persistence | SQLite-backed, in-process |
| Metadata per chunk | `doc_id`, `doc_name`, `page_number`, `passage_index`, `section_title` |

ChromaDB runs embedded inside the FastAPI process — no separate container or network call.

---

### 5. BM25 Hybrid Search

| Property | Value |
|----------|-------|
| Library | `rank-bm25` (BM25Okapi variant) |
| Index | In-memory, rebuilt on startup and after each ingest |
| Tokenisation | Regex — strips punctuation, lowercases |

BM25 excels at exact keyword matches where dense vectors underperform — acronyms, proper nouns, version numbers, and rare technical terms.

---

### 6. Cross-Encoder Reranking — `cross-encoder/ms-marco-MiniLM-L-6-v2`

| Property | Value |
|----------|-------|
| Parameters | ~22M |
| Input | (query, passage) pair |
| Output | Relevance logit → sigmoid probability |
| Runs locally | Yes — CPU |

**Final scoring:**

```
final_score = 0.5 × vector_similarity
            + 0.3 × normalised_bm25
            + 0.2 × cross_encoder_probability
```

**Dynamic chunk selection:** Chunks are included while their score is ≥ 50% of the top chunk's score, up to a hard cap of 5 chunks.

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
| RAM required | ~5 GB (CPU) |
| Context window | 128k tokens |
| Requires API key | No |
| Fully offline | Yes |

Non-streaming path uses grammar-constrained JSON decoding (`LlamaGrammar`) to guarantee valid structured output. Streaming path uses the `NOT_FOUND` sentinel approach.

---

## Features

### Multi-Turn Query Rewriting (`localllm` branch)

Before retrieval, the system rewrites anaphoric follow-up questions into self-contained queries using the conversation history. For example:

> Turn 1: "What are the revenue figures for France?"
> Turn 2: "What about Germany?" → rewritten to "What are the revenue figures for Germany?"

This ensures the retrieval step gets a semantically complete query even when the user references prior context with pronouns or short phrases.

### @Mention Document Scoping

Type `@` in the chat input to scope retrieval to specific documents. Multiple documents can be pinned simultaneously.

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
| Embeddings | nomic-embed-text-v1.5 | nomic-embed-text-v1.5 |
| BM25 | rank-bm25 (Okapi) | rank-bm25 (Okapi) |
| Reranker | ms-marco-MiniLM-L-6-v2 | ms-marco-MiniLM-L-6-v2 |
| LLM | Gemini 2.5 Flash | Phi-4-mini Q4_K_M (llama-cpp-python) |
| PDF parsing | PyMuPDF | PyMuPDF |
| DOCX parsing | python-docx | python-docx |
| Frontend | React 19 + Vite 8 + Tailwind CSS 4 | React 19 + Vite 8 + Tailwind CSS 4 |
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

**Prerequisites:** Docker Desktop, ~6 GB RAM, ~2.5 GB disk for the model

```bash
git checkout localllm

# Download the model once (into the project root ./models/)
pip install huggingface_hub
hf download bartowski/microsoft_Phi-4-mini-instruct-GGUF \
  --include "microsoft_Phi-4-mini-instruct-Q4_K_M.gguf" \
  --local-dir ./models/

docker compose up --build
```

Open **http://localhost:8000**. The model loads on first query (~10–20s cold start on CPU).

---

### Docker Volumes

| Volume | Contents |
|--------|----------|
| `app_data` | SQLite database + ChromaDB index |
| `app_uploads` | Uploaded PDF/DOCX files |
| `hf_cache` | HuggingFace model cache (embeddings + reranker) |
| `./models` (`localllm` only) | GGUF model file (bind mount, read-only) |

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
uv run hf download bartowski/microsoft_Phi-4-mini-instruct-GGUF \
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
| `LLM_N_CTX` | `8192` | Context window tokens |
| `LLM_N_THREADS` | `4` | CPU threads for inference |
| `LLM_N_GPU_LAYERS` | `0` | `0` = CPU only, `-1` = all layers on GPU |
| `LLM_TEMPERATURE` | `0.0` | Sampling temperature |
| `LLM_MAX_TOKENS` | `2048` | Maximum tokens per response |
| `DATABASE_URL` | `sqlite:///./data/app.db` | SQLAlchemy connection string |
| `CHROMA_PATH` | `./data/chroma` | ChromaDB persistence directory |
| `UPLOAD_DIR` | `./uploads` | Uploaded file storage |
| `CORS_ORIGINS` | `http://localhost:5173` | Comma-separated allowed origins, or `*` |
