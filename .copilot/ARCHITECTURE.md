# Architecture — gemma-test (SENDIT Internal Chatbot)

## Overview

Internal logistics chatbot for SENDIT (Moroccan delivery company). Uses a Gemma 4 26B model
served via HuggingFace Transformers, with BM25 category-aware document retrieval over company
procedure docs. Deployed on RunPod GPU infrastructure.

---

## Service Architecture

```
Browser / API Client
        │
        ▼ :8000
┌──────────────────┐
│  FastAPI (api/)  │  Auth, chat endpoint, admin UI
│  uvicorn         │
└────────┬─────────┘
         │ HTTP  localhost:8002
         ▼
┌──────────────────────────────┐
│  serve_gemma4.py (scripts/)  │  OpenAI-compatible inference
│  HuggingFace Transformers    │  /v1/chat/completions
│  Gemma 4 26B-IT              │  /v1/models  /health
└──────────────────────────────┘
```

| Service | Port | Process pattern |
|---------|------|-----------------|
| FastAPI (uvicorn) | 8000 | `uvicorn` |
| Inference server  | 8002 | `serve_gemma4` |

---

## Infrastructure

- **RunPod Pod**: `xkebko0395sada` — 2× A40 GPUs (48 GB VRAM each), $0.88/hr
- **SSH alias**: `runpod2` → `ssh.runpod.io`, user `xkebko0395sada-6441173b`, key `~/.ssh/id_ed25519`
- **Model**: `gemma4-26b-it` at `/workspace/models/gemma4-26b-it` (~52 GB)
- **GPU usage**: Model loads onto first available CUDA device (auto-detected); cuda:0 has been observed
  as unavailable on this pod so the model loads to cuda:1 via `device_map={'': DEVICE}`

---

## Key Files

| File | Purpose |
|------|---------|
| `pod_deploy.py` | Full automated deployment: docs upload, git pull, service restart, e2e test |
| `scripts/serve_gemma4.py` | HuggingFace Transformers inference server (OpenAI-compatible) |
| `core/documents.py` | BM25 category-aware document loader and retrieval |
| `core/llm.py` | GemmaModel client (calls serve_gemma4 HTTP API) |
| `core/pipeline.py` | GemmaPipeline: BM25 retrieval → LLM generation |
| `api/main.py` | FastAPI application: `/chat`, `/categories`, `/health`, `/auth/login` |
| `data/documents/` | Procedure docs in category subdirs (e.g. `procedures/`) |
| `.env` | Environment variables: `VLLM_MODEL_NAME`, `MODEL_DIR`, etc. |

---

## Document System

- Docs stored in `data/documents/<CategoryName>/` subdirectories
- `core/documents.py` (`DocStore`) only processes subdirectories; ignores root-level files
- BM25 retrieval: top-3 docs per category returned for context injection
- Current category: `procedures/` — 10 `.docx` files

---

## Deployment Workflow

```bash
# Full deploy (first time or when docs changed)
python pod_deploy.py

# Redeploy without re-uploading docs (code-only change)
python pod_deploy.py --skip-upload
```

`pod_deploy.py` performs:
1. **(optional)** Tar and upload `data/documents/procedures/` via base64-over-SSH (SFTP blocked by RunPod)
2. Git pull latest code on pod
3. Select model: checks `gemma4-26b-it` first, falls back to `GemMaroc-27b-it`
4. Write `.env` with correct `VLLM_MODEL_NAME`
5. Kill existing processes (`pkill -9 -f 'serve_gemma4'`, `pkill -9 -f 'uvicorn'`)
6. Start `serve_gemma4.py` (background, logs to `logs/vllm_gemma4.log`)
7. Wait for inference server `/health` (pgrep pattern: `serve_gemma4`)
8. Start FastAPI (background, logs to `logs/api.log`)
9. Run e2e test: `/health` → `/categories` → POST `/chat`

---

## Inference Server Details (`scripts/serve_gemma4.py`)

- Transformers version: `5.6.2`
- `apply_chat_template` must use `return_dict=True` (returns `BatchEncoding`; otherwise code fails with `AttributeError`)
- GPU device auto-detection: iterates `cuda:0..N`, picks first that allocates successfully
- Override via env var: `CUDA_DEVICE=cuda:1` (or any device string)
- `device_map={'': DEVICE}` forces all model layers to one device — prevents CPU/meta offload
- Model served as `model_id = os.path.basename(MODEL_DIR)` → `gemma4-26b-it`

---

## Environment Variables (`.env`)

| Variable | Example | Description |
|----------|---------|-------------|
| `VLLM_MODEL_NAME` | `gemma4-26b-it` | Must match `os.path.basename(MODEL_DIR)` in serve_gemma4.py |
| `MODEL_DIR` | `/workspace/models/gemma4-26b-it` | Path to model weights |
| `MAX_NEW_TOKENS` | `1024` | Max generation tokens |
| `TEMPERATURE` | `0.7` | Sampling temperature |
| `CUDA_DEVICE` | *(unset = auto-detect)* | Override GPU device for model loading |

---

## Known Issues & Resolutions

| Issue | Root Cause | Fix |
|-------|-----------|-----|
| `AttributeError: 'BatchEncoding' object has no attribute 'shape'` | `apply_chat_template` with `return_tensors="pt"` returns dict in transformers 5.6.2 | Added `return_dict=True`, extract `inputs["input_ids"]` |
| 195s/91 tokens inference speed | `device_map="auto"` saw cuda:0 as unavailable → CPU offload on 'meta' | Auto-detect first available CUDA device, use `device_map={'': DEVICE}` |
| Upload included 60 flat-root docs | Tarball pointed at `data/documents/` root | Tarball only `data/documents/procedures/` subfolder |
| Model name mismatch (`gemma4` vs `gemma4-26b-it`) | `.env` set wrong name | Fixed to use `os.path.basename(MODEL_DIR)` |
| `pkill`/`pgrep` patterns missed process | Used `vllm` pattern; process is `serve_gemma4` | Changed to `serve_gemma4` pattern |

---

## Checkpoint Rules

- Always read this [ARCHITECTURE.md](ARCHITECTURE.md) before making deployment, inference, or pod-debugging changes.
- The `checkpoint/instructions.md` file records the current operating rules for GPU recovery and temporary file handling.
- Whenever code, docs, environment variables, deployment scripts, or model-loading logic change, update the deployment workflow and redeploy notes in this architecture file.
- Temporary Python files used for diagnostics, checks, or one-off debugging must live in `artifacts/`.
- Do not leave temporary `.py` files in the repository root or in application folders.
- If the RunPod pod exposes an inaccessible `cuda:0`, prefer checking and freeing the blocking GPU process first before applying workaround-based fixes.

---

## SSH Tunneling (local development)

```bash
ssh -L 8000:localhost:8000 -L 8002:localhost:8002 runpod2
# Then access http://localhost:8000 locally
```

---

## Git Repository

`https://github.com/chafiyounes/gemma-test`
# Checkpoint Instructions

## Required Read
- Always read [ARCHITECTURE.md](../ARCHITECTURE.md) before changing deployment, inference, or pod-debugging behavior.

## GPU Fix
- The RunPod pod exposed `cuda:0` in `nvidia-smi`, but that GPU was not actually usable for CUDA allocations.
- `device_map='auto'` on Gemma 4 26B caused CPU offload and very slow inference.
- Transformers 5.6.x `caching_allocator_warmup` also crashed when it tried to touch the inaccessible GPU.
- The working fix is to hide the broken GPU with `CUDA_VISIBLE_DEVICES=1` and load the model with `BitsAndBytesConfig(load_in_8bit=True)` so it fits on the remaining A40.

## Temporary Files
- Any temporary Python files used for diagnostics, checks, or one-off debugging must be placed in the `artifacts/` folder.
- Do not leave temporary `.py` files in the repository root or in application folders.
- Reuse or clean up temporary files in `artifacts/` after the debugging session when possible.
