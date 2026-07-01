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
    gcc g++ cmake libgomp1 libheif-dev libffi-dev \
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

# Install Python dependencies only (skip building the local project package)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Copy application code
COPY backend/ ./backend/

# Copy built frontend
COPY --from=frontend-builder /build/frontend/dist ./frontend/dist

# Create data directories
RUN mkdir -p /data /uploads /models

# Pre-download embedding model at build time so no runtime download is needed
RUN /app/.venv/bin/python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('nomic-ai/nomic-embed-text-v1.5', trust_remote_code=True)"

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
ENV LLM_MODEL_PATH=/models/Llama-3.2-1B-Instruct-Q4_K_M.gguf
ENV LLM_N_CTX=8192
ENV LLM_N_THREADS=4
ENV LLM_N_GPU_LAYERS=0
ENV LLM_TEMPERATURE=0.0
ENV LLM_MAX_TOKENS=2048

# Auto-create persistent volumes when run from Docker Desktop
VOLUME ["/data", "/uploads", "/models"]

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
