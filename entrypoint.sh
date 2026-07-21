#!/bin/bash
set -e

MODEL_DIR="/models"
MODEL_FILE="$MODEL_DIR/microsoft_Phi-4-mini-instruct-Q4_K_M.gguf"

# Check if the model file already exists in the mounted volume
if [ ! -f "$MODEL_FILE" ]; then
    echo "Model not found. Downloading from HuggingFace (~2.5GB, please wait)..."
    huggingface-cli download bartowski/microsoft_Phi-4-mini-instruct-GGUF \
      --include "microsoft_Phi-4-mini-instruct-Q4_K_M.gguf" \
      --local-dir "$MODEL_DIR"
    echo "Download complete."
else
    echo "Model found. Skipping download."
fi

# Execute the main application command (passed from Dockerfile CMD)
exec "$@"
