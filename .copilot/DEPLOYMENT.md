# Deployment

**Canonical deployment + SSH guide:** [`project/DEPLOYMENT.md`](../project/DEPLOYMENT.md)

Architecture and RAG: [`project/ARCHITECTURE.md`](../project/ARCHITECTURE.md) · Product roadmap: [`project/ROADMAP.md`](../project/ROADMAP.md)

| Service | Default port | Notes |
|--------|--------------|--------|
| FastAPI (`uvicorn api.main:app`) | 8000 | Auth, chat, static SPA |
| vLLM (`scripts/start_vllm.sh`) | 8002 | OpenAI-compatible `/v1/chat/completions` |
| SSH tunnel | — | e.g. `-L 8000:localhost:8000 -L 8002:localhost:8002` |

Pod: prefer **vLLM** in `/workspace/vllm-venv`; see `scripts/install_vllm.sh` and `scripts/start_vllm.sh`. Legacy alternative: `scripts/serve_gemma4.py` (Transformers).
