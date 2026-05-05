#!/bin/bash
# First-time pod bootstrap. Do NOT hardcode production passwords in this file.
#
# Before running:
#   export DEPLOY_USER_PASSWORD='…'
#   export DEPLOY_ADMIN_PASSWORD='…'
#   optional: export DEPLOY_SESSION_SECRET='…'  (long random; default generated below)
#
set -euo pipefail
: "${DEPLOY_USER_PASSWORD:?Set DEPLOY_USER_PASSWORD}"
: "${DEPLOY_ADMIN_PASSWORD:?Set DEPLOY_ADMIN_PASSWORD}"
DEPLOY_SESSION_SECRET="${DEPLOY_SESSION_SECRET:-$(openssl rand -hex 32 2>/dev/null || echo change-me-run-openssl-on-pod)}"

cd /workspace
echo "=== Cloning repo ==="
git clone https://github.com/chafiyounes/gemma-test.git || (cd gemma-test && git pull)
echo "=== Installing Python deps ==="
cd /workspace/gemma-test
pip install -r requirements.txt --quiet
echo "=== Installing bitsandbytes for INT8 quantization ==="
pip install bitsandbytes --quiet
echo "=== Creating .env ==="
cat > /workspace/gemma-test/.env << EOF
VLLM_BASE_URL=http://localhost:8002
VLLM_MODEL_NAME=gemma4-26b-it
AVAILABLE_MODELS=gemma4-26b-it
INTERACTIONS_DB_PATH=data/interactions.db
USER_SITE_PASSWORD=${DEPLOY_USER_PASSWORD}
ADMIN_SITE_PASSWORD=${DEPLOY_ADMIN_PASSWORD}
SESSION_SECRET_KEY=${DEPLOY_SESSION_SECRET}
LOG_LEVEL=INFO
MAX_NEW_TOKENS=2048
TEMPERATURE=0.7
TOP_P=0.9
RATE_LIMIT_MAX_REQUESTS=30
RATE_LIMIT_WINDOW_SECONDS=60
VLLM_TIMEOUT=240
EOF
echo "=== Creating directories ==="
mkdir -p /workspace/gemma-test/data
mkdir -p /workspace/gemma-test/logs
echo "=== Fixing script line endings ==="
sed -i 's/\r//' /workspace/gemma-test/scripts/*.sh
sed -i 's/\r//' /workspace/gemma-test/start_all.sh
chmod +x /workspace/gemma-test/scripts/*.sh
chmod +x /workspace/gemma-test/start_all.sh
echo "=== Building web UI ==="
cd /workspace/gemma-test/web_test
npm install --silent
npm run build
echo "=== SETUP COMPLETE ==="
