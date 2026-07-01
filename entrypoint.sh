#!/bin/bash
set -e

MODEL_DIR="/models"
MODEL_FILE="$MODEL_DIR/Llama-3.2-1B-Instruct-Q4_K_M.gguf"

# Check if the model file already exists in the mounted volume
if [ ! -f "$MODEL_FILE" ]; then
    echo "Model not found. Downloading from HuggingFace (~700MB, please wait)..."
    hf download bartowski/Llama-3.2-1B-Instruct-GGUF \
      --include "Llama-3.2-1B-Instruct-Q4_K_M.gguf" \
      --local-dir "$MODEL_DIR"
    echo "Download complete."
else
    echo "Model found. Skipping download."
fi

# Execute the main application command (passed from Dockerfile CMD)
exec "$@"
