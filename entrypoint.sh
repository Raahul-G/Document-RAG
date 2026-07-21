#!/bin/bash
set -e

# ── 1. Phi-4-mini GGUF model ──────────────────────────────────────────────────
MODEL_DIR="/models"
MODEL_FILE="$MODEL_DIR/microsoft_Phi-4-mini-instruct-Q4_K_M.gguf"

if [ ! -f "$MODEL_FILE" ]; then
    echo "==> Phi-4-mini not found. Downloading from HuggingFace (~2.5 GB)..."
    huggingface-cli download bartowski/microsoft_Phi-4-mini-instruct-GGUF \
      --include "microsoft_Phi-4-mini-instruct-Q4_K_M.gguf" \
      --local-dir "$MODEL_DIR"
    echo "==> Phi-4-mini download complete."
else
    echo "==> Phi-4-mini found. Skipping download."
fi

# ── 2. FastEmbed ONNX models ──────────────────────────────────────────────────
# FASTEMBED_CACHE_PATH=/data/fastembed_cache (set in Dockerfile ENV).
# Models persist in the app_data volume — downloaded once, reused on restart.

echo "==> Checking nomic-ai/nomic-embed-text-v1.5 (embedding model, ~270 MB)..."
python -c "
from fastembed import TextEmbedding
TextEmbedding('nomic-ai/nomic-embed-text-v1.5')
print('==> Embedding model ready.')
"

echo "==> Checking Xenova/ms-marco-MiniLM-L-6-v2 (cross-encoder reranker, ~23 MB)..."
python -c "
from fastembed.rerank.cross_encoder import TextCrossEncoder
TextCrossEncoder(model_name='Xenova/ms-marco-MiniLM-L-6-v2')
print('==> Cross-encoder ready.')
"

# ── 3. Start the application ──────────────────────────────────────────────────
exec "$@"
