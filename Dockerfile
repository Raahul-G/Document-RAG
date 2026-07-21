# syntax=docker/dockerfile:1
# Stage 1: Build frontend
FROM node:20-alpine AS frontend-builder
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Runtime
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ cmake libgomp1 libffi-dev \
    libgl1 libglib2.0-0 \
    default-jre-headless \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Prevent uv from downloading its own Python (use the system Python)
ENV UV_PYTHON_DOWNLOADS=never
ENV UV_PYTHON=python3.12

# Ensure llama-cpp-python builds for CPU only (no BLAS, no CUDA)
ENV GGML_BLAS=OFF
ENV GGML_CUDA=OFF

# Install Python dependencies — BuildKit cache mount keeps downloaded wheels across builds
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# Copy application code
COPY backend/ ./backend/

# Copy built frontend
COPY --from=frontend-builder /build/frontend/dist ./frontend/dist

# Create data directories
RUN mkdir -p /data /uploads /models

# Copy and register the startup script
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV PATH="/app/.venv/bin:$PATH"

# Baked-in defaults — no .env file needed
ENV CORS_ORIGINS=*
ENV DATABASE_URL=sqlite:////data/app.db
ENV CHROMA_PATH=/data/chroma
ENV UPLOAD_DIR=/uploads
ENV LLM_MODEL_PATH=/models/microsoft_Phi-4-mini-instruct-Q4_K_M.gguf
ENV LLM_N_CTX=8192
ENV LLM_N_THREADS=4
ENV LLM_N_GPU_LAYERS=0
ENV LLM_TEMPERATURE=0.0
ENV LLM_MAX_TOKENS=2048
ENV BM25_PKL_PATH=/data/bm25.pkl
ENV FASTEMBED_CACHE_PATH=/data/fastembed_cache

# Auto-create persistent volumes when run from Docker Desktop
VOLUME ["/data", "/uploads", "/models"]

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
