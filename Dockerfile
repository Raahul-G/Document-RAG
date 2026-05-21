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

# Install Python dependencies only (skip building the local project package)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Copy application code
COPY backend/ ./backend/

# Copy built frontend
COPY --from=frontend-builder /build/frontend/dist ./frontend/dist

# Create data directories
RUN mkdir -p /data /uploads

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
