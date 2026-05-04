# Copilot Instructions

## Required Reading
- Always read [.copilot/ARCHITECTURE.md](../.copilot/ARCHITECTURE.md) before making deployment, inference, or pod-debugging changes.
- Always read [.copilot/DEPLOYMENT.md](../.copilot/DEPLOYMENT.md) for current port mappings, SSH credentials, and deployment procedures.

## Architecture Essentials
- **Inference server** (`scripts/serve_gemma4.py`) runs on **port 8002** — NOT 8001.
- **FastAPI API** (`api/main.py`) runs on **port 8000** and serves the built React SPA.
- The model uses **INT8 quantization** via bitsandbytes with `device_map="auto"` across **two A40 GPUs**.
- All 10 SOP procedure documents are injected into every prompt via `build_all_docs_context()` in `core/documents.py` — no BM25 top-k filtering.

## SSH to RunPod
- RunPod SSH gateway **requires a PTY**. Never use `ssh user@host "command"` — it will fail with "Your SSH client doesn't support PTY".
- Use `scripts/pod_cmd.py` (paramiko-based) for automated commands, or connect interactively.
- Current SSH user: `l8lnmi6ofx0tpz-64411278@ssh.runpod.io` with key `~/.ssh/id_ed25519`.

## Code Change Rules
- When any code, docs, environment variables, deployment scripts, or model-loading logic changes, update:
  - [.copilot/ARCHITECTURE.md](../.copilot/ARCHITECTURE.md)
  - [.copilot/DEPLOYMENT.md](../.copilot/DEPLOYMENT.md)
- Temporary Python files used for diagnostics, checks, or one-off debugging must be placed in `artifacts/`.
- Do not leave temporary `.py` files in the repository root or in application folders.

## Frontend
- The web frontend is a React SPA in `web_test/` built with Vite.
- `vite.config.js` has a proxy configuration that forwards `/auth`, `/chat`, `/health`, `/categories`, `/feedback`, etc. to `localhost:8000` during development.
- In production, FastAPI serves the built `dist/` directory directly.
- The `api.js` service handles authentication cookies, feedback (204 No Content), and debug RAG flags.

## Key Dependencies (on pod)
- Python: `transformers`, `torch`, `accelerate`, `bitsandbytes`, `fastapi`, `uvicorn`, `httpx`, `python-docx`
- System: `tmux`, Node.js 20+ (for frontend build)
- These are listed in `requirements.txt` — install via `python3 -m pip install -r requirements.txt`

## Common Gotchas
- **Windows line endings**: Always run `sed -i 's/\r//' scripts/*.sh start_all.sh` after pulling on the pod.
- **VLLM_MODEL_NAME in .env**: Must match the model ID the inference server registers (check `/v1/models`).
- **`/feedback` returns 204**: The frontend must NOT try to parse JSON from this endpoint.
