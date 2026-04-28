#!/bin/bash
set -e
cd /workspace
echo "=== Cloning repo ==="
git clone https://github.com/chafiyounes/gemma-test.git || (cd gemma-test && git pull)
echo "=== Installing Python deps ==="
cd /workspace/gemma-test
pip install -r requirements.txt --quiet
echo "=== Installing vLLM ==="
pip install "vllm>=0.5.0" --quiet
echo "=== Creating .env ==="
cat > /workspace/gemma-test/.env << 'ENVEOF'
VLLM_BASE_URL=http://localhost:8001
VLLM_MODEL_NAME=gemma
AVAILABLE_MODELS=gemma,gemmaroc,atlaschat
INTERACTIONS_DB_PATH=data/interactions.db
USER_SITE_PASSWORD=user1234
ADMIN_SITE_PASSWORD=admin1234
SESSION_SECRET_KEY=gemma-test-secret-key-2026
LOG_LEVEL=INFO
MAX_TOKENS=512
TEMPERATURE=0.7
RATE_LIMIT_REQUESTS=20
RATE_LIMIT_WINDOW=60
ENVEOF
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
