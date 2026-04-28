#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# download_models.sh  —  Download Gemma models + fine-tunes to /workspace
#
# Usage:
#   bash scripts/download_models.sh gemma        # base Gemma 3 27B-IT
#   bash scripts/download_models.sh gemmaroc     # GemMaroc-27b-it fine-tune
#   bash scripts/download_models.sh atlaschat    # Atlas-Chat-27B (base HF)
#   bash scripts/download_models.sh all          # all three
#
# Requirements:
#   HF_TOKEN env var set, OR model is public (Gemma requires acceptance of ToS)
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

MODEL_DIR="/workspace/models"
mkdir -p "$MODEL_DIR"

HF_TOKEN="${HF_TOKEN:-}"
if [[ -z "$HF_TOKEN" ]]; then
    echo "⚠  HF_TOKEN not set. Gated models (Gemma) will fail to download."
    echo "   Export it first:  export HF_TOKEN=hf_xxxx"
fi

download_model() {
    local repo_id="$1"
    local local_name="$2"
    local target="$MODEL_DIR/$local_name"

    if [[ -d "$target" && -n "$(ls -A "$target" 2>/dev/null)" ]]; then
        echo "✓  $local_name already exists at $target — skipping"
        return
    fi

    echo ""
    echo "──────────────────────────────────────────"
    echo "  Downloading  $repo_id"
    echo "  → $target"
    echo "──────────────────────────────────────────"

    mkdir -p "$target"
    python3 - <<PYEOF
import os, sys
from huggingface_hub import snapshot_download

repo = "$repo_id"
dest = "$target"
token = os.environ.get("HF_TOKEN") or None

print(f"Downloading {repo} ...", flush=True)
snapshot_download(
    repo_id=repo,
    local_dir=dest,
    token=token,
    ignore_patterns=["*.msgpack", "flax_model*", "tf_model*", "rust_model*"],
)
print(f"✓ Done  →  {dest}", flush=True)
PYEOF
}

TARGET="${1:-all}"

case "$TARGET" in
    gemma)
        # NOTE: If Gemma 4 is released by the time you run this, update the
        # repo ID below (e.g. google/gemma-4-27b-it).
        download_model "google/gemma-3-27b-it"  "gemma-3-27b-it"
        ;;
    gemmaroc)
        download_model "AbderrahmanSkiredj1/GemMaroc-27b-it" "GemMaroc-27b-it"
        ;;
    atlaschat)
        # Using the base (non-GGUF) HF version for vLLM compatibility
        download_model "BounharAbdelaziz/Atlas-Chat-27B" "Atlas-Chat-27B"
        ;;
    all)
        download_model "google/gemma-3-27b-it"                "gemma-3-27b-it"
        download_model "AbderrahmanSkiredj1/GemMaroc-27b-it"  "GemMaroc-27b-it"
        download_model "BounharAbdelaziz/Atlas-Chat-27B"       "Atlas-Chat-27B"
        ;;
    *)
        echo "Unknown target: $TARGET"
        echo "Usage: bash scripts/download_models.sh [gemma|gemmaroc|atlaschat|all]"
        exit 1
        ;;
esac

echo ""
echo "✓ Download(s) complete.  Models stored in $MODEL_DIR"
ls -lh "$MODEL_DIR"
