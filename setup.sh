#!/bin/bash
# setup.sh
# Run this ONCE before building Docker or running locally.
# Downloads the Piper TTS voice model files into the voices/ directory.

set -e

echo "======================================"
echo "  FreshMart Voice AI - Setup Script"
echo "======================================"

# ── Step 1: Create voices directory ───────────────────────────────────────────
echo ""
echo "[1/4] Creating voices/ directory..."
mkdir -p voices

# ── Step 2: Download Piper voice model ────────────────────────────────────────
echo ""
echo "[2/4] Downloading Piper TTS voice model (en_US-lessac-medium)..."
echo "      This is ~60MB, please wait..."

BASE_URL="https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium"
ONNX_FILE="voices/en_US-lessac-medium.onnx"
JSON_FILE="voices/en_US-lessac-medium.onnx.json"

if [ -f "$ONNX_FILE" ]; then
    echo "      $ONNX_FILE already exists, skipping."
else
    curl -L --progress-bar "$BASE_URL/en_US-lessac-medium.onnx" -o "$ONNX_FILE"
    echo "      Downloaded: $ONNX_FILE"
fi

if [ -f "$JSON_FILE" ]; then
    echo "      $JSON_FILE already exists, skipping."
else
    curl -L --progress-bar "$BASE_URL/en_US-lessac-medium.onnx.json" -o "$JSON_FILE"
    echo "      Downloaded: $JSON_FILE"
fi

# ── Step 3: Check Ollama ───────────────────────────────────────────────────────
echo ""
echo "[3/4] Checking Ollama..."
if command -v ollama &> /dev/null; then
    echo "      Ollama found. Pulling qwen2.5:1.5b model..."
    ollama pull qwen2.5:1.5b
    echo "      Model ready."
else
    echo "      WARNING: Ollama not found in PATH."
    echo "      Install from: https://ollama.com"
    echo "      Then run:  ollama pull qwen2.5:1.5b"
fi

# ── Step 4: Rename .gitignore if needed ───────────────────────────────────────
echo ""
echo "[4/4] Checking .gitignore..."
if [ -f "_gitignore" ] && [ ! -f ".gitignore" ]; then
    cp "_gitignore" ".gitignore"
    echo "      Renamed _gitignore -> .gitignore"
else
    echo "      .gitignore OK"
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "======================================"
echo "  Setup complete!"
echo "======================================"
echo ""
echo "Next steps:"
echo ""
echo "  Option A — Run with Docker (recommended):"
echo "    docker build -t freshmart-api ."
echo "    docker run -p 8000:8000 --add-host=host.docker.internal:host-gateway freshmart-api"
echo ""
echo "  Option B — Run locally (without Docker):"
echo "    pip install -r requirements.txt"
echo "    uvicorn main:app --reload --port 8000"
echo ""
echo "  Then open index.html in your browser."
echo "  API health check: http://localhost:8000/health"
echo ""
