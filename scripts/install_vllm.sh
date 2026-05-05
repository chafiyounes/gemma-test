#!/usr/bin/env bash
# Install vLLM 0.19.0 (the release that adds Gemma 4 support) into an
# isolated venv at /workspace/vllm-venv so the existing transformers
# environment used by the FastAPI backend stays untouched.
set -euo pipefail

VENV=/workspace/vllm-venv
WHEEL_INDEX=https://wheels.vllm.ai/0.19.0/cu129
TORCH_INDEX=https://download.pytorch.org/whl/cu129

echo "── creating venv at $VENV ──"
if [[ ! -d "$VENV" ]]; then
    python3.11 -m venv "$VENV"
fi
# shellcheck source=/dev/null
source "$VENV/bin/activate"

echo "── upgrading pip / build tools ──"
pip install -q -U pip wheel setuptools

echo "── installing vllm 0.19.0 (cu129) ──"
pip install -U vllm==0.19.0 \
    --extra-index-url "$WHEEL_INDEX" \
    --extra-index-url "$TORCH_INDEX" \
    --index-strategy unsafe-best-match \
    || pip install -U vllm==0.19.0 \
        --extra-index-url "$WHEEL_INDEX" \
        --extra-index-url "$TORCH_INDEX"

echo
echo "── installed package versions ──"
python3 - <<'PY'
import importlib
for mod in ["torch", "vllm", "transformers", "flashinfer"]:
    try:
        m = importlib.import_module(mod)
        print(f"  {mod}: {getattr(m, '__version__', '?')}")
    except Exception as e:
        print(f"  {mod}: NOT INSTALLED ({type(e).__name__}: {e})")
print(f"  cuda available: {__import__('torch').cuda.is_available()}, "
      f"n_gpu={__import__('torch').cuda.device_count()}")
PY

echo "── done ──"
