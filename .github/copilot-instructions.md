# Copilot Instructions

## Required Reading
- Always read [`project/ARCHITECTURE.md`](../project/ARCHITECTURE.md) before deployment, inference, or pod-debugging changes (diagrams + full stack).
- [.copilot/ARCHITECTURE.md](../.copilot/ARCHITECTURE.md) and [.copilot/DEPLOYMENT.md](../.copilot/DEPLOYMENT.md) point to the same canonical doc.

## Architecture Essentials
- **Inference (preferred on pod):** **vLLM** on **port 8002** — `scripts/start_vllm.sh` (tensor parallel across 2× A40). **Legacy:** `scripts/serve_gemma4.py` (Transformers).
- **FastAPI** (`api/main.py`) on **port 8000** serves API + built React SPA.
- **RAG:** For each category, if corpus size ≤ `RAG_FULL_CATEGORY_MAX_CHARS`, **all** docs in that category are injected (`build_all_docs_context`); else **BM25** top-k. **BM25 query expansion** (French logistics hints) applies only when the user language bucket is **French or Darija** — English stays English-only (`core/llm.py`).

## SSH to RunPod
- RunPod SSH gateway **requires a PTY**. Never use `ssh user@host "command"` — it will fail with "Your SSH client doesn't support PTY".
- Use `scripts/pod_cmd.py` (paramiko-based) for automated commands, or connect interactively.
- Current SSH user: `l8lnmi6ofx0tpz-64411278@ssh.runpod.io` with key `~/.ssh/id_ed25519`.

## Code Change Rules
- When any code, docs, environment variables, deployment scripts, or model-loading logic changes, update **`project/ARCHITECTURE.md`** (and keep `.copilot/*.md` pointers accurate if needed).
- Temporary Python files used for diagnostics, checks, or one-off debugging must be placed in `artifacts/`.
- Do not leave temporary `.py` files in the repository root or in application folders.

## Frontend
- The web frontend is a React SPA in `web_test/` built with Vite.
- `vite.config.js` has a proxy configuration that forwards `/auth`, `/chat`, `/health`, `/categories`, `/feedback`, etc. to `localhost:8000` during development.
- In production, FastAPI serves the built `dist/` directory directly.
- The `api.js` service handles authentication cookies, feedback (204 No Content), and debug RAG flags.

## Key Dependencies (on pod)
- **Inference:** **vLLM** (preferred) in isolated venv — see `scripts/install_vllm.sh`; optional `serve_gemma4.py` uses `transformers`, `torch`, `accelerate`, `bitsandbytes`.
- **API:** `fastapi`, `uvicorn`, `httpx`, `python-docx`, `pydantic-settings`
- System: `tmux`, Node.js 20+ (for frontend build)
- These are listed in `requirements.txt` — install via `python3 -m pip install -r requirements.txt`

## Common Gotchas
- **Windows line endings**: Always run `sed -i 's/\r//' scripts/*.sh start_all.sh` after pulling on the pod.
- **VLLM_MODEL_NAME in .env**: Must match the model ID the inference server registers (check `/v1/models`).
- **`/feedback` returns 204**: The frontend must NOT try to parse JSON from this endpoint.
