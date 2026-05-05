#!/usr/bin/env bash
# Apply files staged in /tmp/sync to the live project tree on the pod.
# Strips CRLF and chmod's scripts.
set -uo pipefail
PROJ="/workspace/gemma-test"
SRC="/tmp/sync"

echo "── apply /tmp/sync → $PROJ ──"
mkdir -p "$PROJ/scripts" "$PROJ/core" "$PROJ/app_config"

for f in serve_gemma4.py start_vllm.sh pod_restart_only.sh pod_quick_test.sh \
         pod_chat_smoke.sh install_vllm.sh bench_vllm.py \
         diag_generate.py diag_set_submodule.py diag_token.py diag_gemma4.py \
         pod_deploy_and_test.sh; do
    if [[ -f "$SRC/$f" ]]; then
        sed 's/\r$//' "$SRC/$f" > "$PROJ/scripts/$f"
        echo "  scripts/$f"
    fi
done
chmod +x "$PROJ/scripts/"*.sh 2>/dev/null || true

for f in llm.py documents.py pipeline.py; do
    if [[ -f "$SRC/$f" ]]; then
        sed 's/\r$//' "$SRC/$f" > "$PROJ/core/$f"
        echo "  core/$f"
    fi
done

if [[ -f "$SRC/settings.py" ]]; then
    sed 's/\r$//' "$SRC/settings.py" > "$PROJ/app_config/settings.py"
    echo "  app_config/settings.py"
fi

if [[ -f "$SRC/requirements.txt" ]]; then
    sed 's/\r$//' "$SRC/requirements.txt" > "$PROJ/requirements.txt"
    echo "  requirements.txt"
fi

echo "── done ──"
