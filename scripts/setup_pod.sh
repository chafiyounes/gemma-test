#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# setup_pod.sh  —  One-time system setup for the gemma-test RunPod pod
# Run this ONCE after first connecting to a fresh pod.
# Usage:  bash scripts/setup_pod.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

echo "══════════════════════════════════════════════════"
echo "  Gemma Test Pod — System Setup"
echo "══════════════════════════════════════════════════"

# 1. System packages
apt-get update -qq
apt-get install -y --no-install-recommends \
    curl wget git build-essential screen htop nvtop tmux

# 2. Upgrade pip
pip install --upgrade pip

# 3. Install vLLM (OpenAI-compatible inference server)
#    vLLM 0.5.x supports Gemma 3 out of the box.
pip install "vllm>=0.5.0" --extra-index-url https://download.pytorch.org/whl/cu121

# 4. Install Python API dependencies
pip install \
    fastapi==0.115.0 \
    "uvicorn[standard]==0.30.0" \
    pydantic==2.7.0 \
    pydantic-settings==2.3.0 \
    httpx==0.27.0 \
    python-dotenv==1.0.1

# 5. Create workspace directories
mkdir -p /workspace/gemma-test/data/models
mkdir -p /workspace/gemma-test/data/db
mkdir -p /workspace/gemma-test/logs

echo ""
echo "✓ System setup complete"
echo "  Next steps:"
echo "  1.  bash scripts/download_gemma.sh          # download base model"
echo "  2.  bash scripts/start_vllm.sh gemma        # start vLLM with Gemma"
echo "  3.  bash scripts/start_api.sh               # start FastAPI"
