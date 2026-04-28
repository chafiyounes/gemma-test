# Gemma Test Deployment Guide

## Overview

This project tests Gemma (and Darija-fine-tuned variants) for Moroccan Arabic (Darija) and Arabizi comprehension. It reuses the pipeline architecture from `darija-chatbot` but strips out RAG, Redis and translation — focusing purely on raw LLM capability.

| Service | Description | Port |
|---------|-------------|------|
| **vLLM** | Inference server (Gemma 3 27B or fine-tunes) | 8001 |
| **FastAPI** | Chat API + admin | 8000 |

SQLite is used for persistence (`data/interactions.db`). No external databases needed.

---

## Pod Details

SSH host `runpod2` is configured in `~/.ssh/config`:

```
Host runpod2
    HostName ssh.runpod.io
    User xkebko0395sada-6441173b
    IdentityFile ~/.ssh/id_ed25519
```

---

## Phase 1 — First-time Pod Setup

```bash
ssh runpod2
cd /workspace

# Clone or upload the project
git clone <your-repo> gemma-test
# OR  scp -r "C:/Users/pc gamer/OneDrive/Desktop/full project/gemma-test" runpod2:/workspace/

cd /workspace/gemma-test

# Install system deps + Python packages
bash scripts/setup_pod.sh
```

---

## Phase 2 — Download Model(s)

```bash
# Base Gemma (requires HuggingFace account + ToS acceptance at hf.co/google/gemma-3-27b-it)
export HF_TOKEN=hf_YOUR_TOKEN_HERE
bash scripts/download_models.sh gemma

# Fine-tuned Darija models (public, no token needed)
bash scripts/download_models.sh gemmaroc
bash scripts/download_models.sh atlaschat

# Or download all at once:
bash scripts/download_models.sh all
```

> **Note on Gemma 4:** The download script targets `google/gemma-3-27b-it`. If Gemma 4 is
> available on HuggingFace by the time you run this, update the repo ID in
> `scripts/download_models.sh` (the `gemma` case) and update `VLLM_MODEL_NAME` in `.env`.

### Atlas-Chat GGUF note

The HuggingFace link you shared (`mradermacher/Atlas-Chat-27B-GGUF`) is a quantized GGUF
version. **vLLM does not support GGUF directly.** We use the original BF16 model
`BounharAbdelaziz/Atlas-Chat-27B` instead. If you specifically want the GGUF version for
llama.cpp, it would require a separate llama.cpp server.

---

## Phase 3 — Start Services

```bash
cd /workspace/gemma-test

# Start both vLLM + API (using base Gemma by default)
bash start_all.sh gemma

# Attach to watch logs
tmux attach -t gemma-test
```

Switch between models by restarting vLLM:
```bash
# In a separate tmux window:
bash scripts/start_vllm.sh gemmaroc
# Then update .env: VLLM_MODEL_NAME=GemMaroc-27b-it
# Then restart API: bash scripts/start_api.sh
```

---

## Phase 4 — SSH Tunnels (access from local machine)

```powershell
# PowerShell — keep this terminal open while testing
ssh -L 8000:localhost:8000 -L 8001:localhost:8001 runpod2
```

After the tunnel is open:
- **Chat UI**: run `npm run build` in `web_test/`, then open `http://localhost:8000`
- **Admin panel**: `http://localhost:8000/admin` (password: `admin1234` from `.env`)
- **API docs**: `http://localhost:8000/docs`

For local dev (hot-reload):
```powershell
cd "C:\Users\pc gamer\OneDrive\Desktop\full project\gemma-test\web_test"
npm install
npm run dev    # http://localhost:5173
```
Set the API URL in the web UI settings to `http://localhost:8000`.

---

## Phase 5 — Run Capability Tests

With vLLM running:

```bash
# On the pod:
cd /workspace/gemma-test

# Test base Gemma
python3 scripts/test_capabilities.py --model gemma

# Test GemMaroc fine-tune (must restart vLLM first with gemmaroc)
bash scripts/start_vllm.sh gemmaroc
python3 scripts/test_capabilities.py --model gemmaroc

# Test Atlas-Chat fine-tune
bash scripts/start_vllm.sh atlaschat
python3 scripts/test_capabilities.py --model atlaschat
```

Results are saved to `/workspace/gemma-test/logs/test_results_<timestamp>.json`.

---

## What We're Testing

### Darija (Arabic script)
- Standard Moroccan dialect greetings and questions
- Code-switching between Darija and French
- Complex multi-part questions about travel, money, etc.

### Arabizi (Darija in Latin script with digit substitutions)
- `3` = ع (ain), `7` = ح (ha), `9` = ق (qaf)
- Mixed Arabizi + French (very common in WhatsApp messages)
- Slang and colloquial phrasing

### Expected findings (hypothesis to verify)

| Model | Darija | Arabizi |
|-------|--------|---------|
| **Gemma 3 27B base** | Probably understands MSA, may struggle with Darija | Likely limited — Arabizi is underrepresented in training data |
| **GemMaroc-27b-it** | Should be significantly better (fine-tuned on Moroccan data) | Unclear — depends on whether training included Arabizi |
| **Atlas-Chat-27B** | Fine-tuned on Moroccan dialect data, should handle well | Likely limited unless specifically trained on Arabizi |

---

## Model Switching Reference

Update `.env` on the pod + restart API when switching the vLLM model:

| vLLM command | `.env` value |
|---|---|
| `bash scripts/start_vllm.sh gemma` | `VLLM_MODEL_NAME=gemma` |
| `bash scripts/start_vllm.sh gemmaroc` | `VLLM_MODEL_NAME=gemmaroc` |
| `bash scripts/start_vllm.sh atlaschat` | `VLLM_MODEL_NAME=atlaschat` |

The served name is passed via `--served-model-name` in the vLLM launch script, so these
short names work fine. The admin `GET /models` endpoint shows what's currently set.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `vLLM OOM` | Reduce `MAX_MODEL_LEN` in `start_vllm.sh`, or use `--dtype float16` |
| `API 503` | vLLM still loading — wait ~90s and retry `curl http://localhost:8000/health` |
| `Login fails` | Check `ADMIN_SITE_PASSWORD` in `.env` matches what you type |
| `CUDA out of memory on 27B` | Pod has <48GB VRAM; use smaller quantization or a different size |
