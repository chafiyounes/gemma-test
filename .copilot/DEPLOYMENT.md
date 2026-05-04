# Gemma Test — Deployment Guide

## Architecture

| Service | Description | Port |
|---------|-------------|------|
| **serve_gemma4.py** | Transformers inference server (INT8 quantized, dual-GPU) | **8002** |
| **FastAPI API** | Chat API + auth + admin + SPA serving | **8000** |
| **Web Frontend** | React SPA (Vite build → served by FastAPI from `dist/`) | via 8000 |

The model (Gemma 4 26B-IT) is loaded with **INT8 quantization** via bitsandbytes across **both A40 GPUs** using `device_map="auto"`. Each GPU uses ~25 GB VRAM.

All 10 SOP procedure documents from `data/documents/procedures/` are injected into every prompt as full-text context (no BM25 filtering).

SQLite is used for persistence (`data/interactions.db`). No Redis, no external DB.

---

## Current Pod

SSH user: `l8lnmi6ofx0tpz-64411278@ssh.runpod.io`
Key: `~/.ssh/id_ed25519`

> **Important**: RunPod's SSH gateway requires a PTY. Standard `ssh user@host "command"` does NOT work. Use the `scripts/pod_cmd.py` helper or connect interactively.

---

## One-Click Deploy (from local machine)

```powershell
cd "C:\Users\pc gamer\OneDrive\Desktop\full project\gemma-test"
python scripts/deploy_runner.py
```

This script connects via paramiko (PTY), and:
1. Installs system deps (tmux, Node.js 20)
2. Installs Python deps (`transformers`, `torch`, `bitsandbytes`, etc.)
3. Pulls latest code from GitHub
4. Builds the React frontend (`npm run build`)
5. Starts all services via `bash start_all.sh gemma4`

---

## Manual Deploy (step-by-step on pod)

### 1. Connect interactively

```bash
ssh -i ~/.ssh/id_ed25519 l8lnmi6ofx0tpz-64411278@ssh.runpod.io
```

### 2. Install system dependencies (first time only)

```bash
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y tmux

# Node.js 20 (for frontend build)
curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | \
  gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg --batch --yes
echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" \
  | tee /etc/apt/sources.list.d/nodesource.list
apt-get update && apt-get install nodejs -y
```

### 3. Pull code and install Python deps

```bash
cd /workspace/gemma-test
git pull origin main
python3 -m pip install -r requirements.txt
python3 -m pip install bitsandbytes accelerate
```

### 4. Build frontend

```bash
cd web_test && npm install && npm run build && cd ..
```

### 5. Fix line endings and start

```bash
sed -i 's/\r//' scripts/*.sh start_all.sh
chmod +x scripts/*.sh start_all.sh
bash start_all.sh gemma4
```

### 6. Monitor

```bash
tmux attach -t gemma-test          # see both windows
# Ctrl+B then 0 → vLLM window
# Ctrl+B then 1 → API window
# Ctrl+B then D → detach
```

---

## Access from Local Machine

Open an SSH tunnel:

```powershell
ssh -i ~/.ssh/id_ed25519 -L 8000:localhost:8000 l8lnmi6ofx0tpz-64411278@ssh.runpod.io
```

Then:
- **Chat UI**: http://localhost:8000 (login: `user1234`)
- **Admin panel**: http://localhost:8000/admin (login: `admin1234`)
- **API docs**: http://localhost:8000/docs
- **Health**: http://localhost:8000/health

For local frontend dev (hot-reload):
```powershell
cd web_test
npm run dev    # http://localhost:5173
```
The Vite dev server proxies API calls to `localhost:8000` automatically (configured in `vite.config.js`).

---

## Health Checks

```bash
# From pod (or via pod_cmd.py):
curl http://localhost:8002/health   # → {"status":"ok","model":"gemma4-26b-it"}
curl http://localhost:8000/health   # → {"status":"ok","model_available":true,...}

# Quick GPU check:
nvidia-smi --query-gpu=index,name,memory.used,memory.total --format=csv,noheader
```

Using the helper from local machine:
```powershell
python scripts/pod_cmd.py "curl -s http://localhost:8002/health" "curl -s http://localhost:8000/health"
```

---

## Model Switching

```bash
# On the pod:
bash scripts/start_vllm.sh gemmaroc    # or: gemma, atlaschat, gemma4
bash scripts/start_api.sh
```

| Command | Model |
|---------|-------|
| `bash scripts/start_vllm.sh gemma4` | `/workspace/models/gemma4-26b-it` |
| `bash scripts/start_vllm.sh gemma` | `/workspace/models/gemma-3-27b-it` |
| `bash scripts/start_vllm.sh gemmaroc` | `/workspace/models/GemMaroc-27b-it` |
| `bash scripts/start_vllm.sh atlaschat` | `/workspace/models/Atlas-Chat-27B` |

---

## Key Configuration

### .env (on pod at `/workspace/gemma-test/.env`)

```env
VLLM_BASE_URL=http://localhost:8002
VLLM_MODEL_NAME=gemma4-26b-it
USER_SITE_PASSWORD=user1234
ADMIN_SITE_PASSWORD=admin1234
MAX_NEW_TOKENS=1024
TEMPERATURE=0.7
TOP_P=0.9
```

### Port Map

| Port | Service | Notes |
|------|---------|-------|
| 8002 | `serve_gemma4.py` | Transformers inference (OpenAI-compatible API) |
| 8000 | FastAPI | Chat API + serves built frontend SPA |
| 5173 | Vite dev | Local dev only (proxies to 8000) |

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `npm: command not found` | Install Node.js 20 (see Step 2 above) |
| `tmux: command not found` | `apt-get install -y tmux` |
| `ModuleNotFoundError: No module named 'transformers'` | `python3 -m pip install transformers torch accelerate bitsandbytes` |
| `Your SSH client doesn't support PTY` | Use `scripts/pod_cmd.py` or connect interactively (not `ssh user@host "cmd"`) |
| `git pull` fails with merge conflict | `git stash && git pull origin main` or `git reset --hard origin/main` |
| vLLM OOM | Reduce `MAX_MODEL_LEN` in `start_vllm.sh`, or check CUDA_VISIBLE_DEVICES |
| API returns 503 | Model still loading — wait ~2-3 min after `start_all.sh` |
| Web shows blank page | Run `npm run build` in `web_test/` then restart API |
| Login fails | Check `USER_SITE_PASSWORD` / `ADMIN_SITE_PASSWORD` in `.env` |
| Windows `\r\n` line endings break bash | `sed -i 's/\r//' scripts/*.sh start_all.sh` |
