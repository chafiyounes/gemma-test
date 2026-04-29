# Deployment Issues — 2026-04-28

## Overview
First full deployment attempt on RunPod pod `xkebko0395sada` (2× A40, $0.88/hr).
Target: serve **GemMaroc-27b-it** via vLLM + FastAPI + web UI.

---

## Issue 1 — vLLM crash: `OSError: [Errno 98] Address already in use` on port 8001

### Symptom
vLLM started, printed its banner, then immediately crashed:
```
OSError: [Errno 98] Address already in use
  File ".../vllm/entrypoints/openai/api_server.py", line 504, in create_server_socket
    sock.bind(addr)
```

### Root Cause
RunPod exposes a **sidecar service already bound to port 8001** on every pod.
It responds 200 to `GET /health` (which fooled our polling loop into thinking vLLM was ready)
but returns `405 Method Not Allowed` on `POST /v1/chat/completions` — not vLLM at all.

### Fix Applied
Changed vLLM port from **8001 → 8002** in `scripts/start_vllm.sh` and `scripts/start_api.sh`.
Updated `.env` `VLLM_BASE_URL=http://localhost:8002`.
The SSH tunnel must also forward port 8002:
```bash
ssh -L 8000:localhost:8000 -L 8002:localhost:8002 runpod2
```
**TODO:** Update SSH tunnel command in README / DEPLOYMENT.md.

### Commit
`a0187b7` — fix: vLLM on port 8002 (avoid stale 8001 sidecar)

---

## Issue 2 — `git reset --hard origin/main` failing on pod

### Symptom
```
fatal: ambiguous argument 'origin/main': unknown revision or path not in the working tree.
```

### Root Cause
The pod's git clone was done without a named remote branch reference (`git clone --depth 1 ...`),
so `origin/main` is not a known ref locally.

### Fix Applied
Changed reset command from:
```bash
git reset --hard origin/main
```
to:
```bash
git fetch origin main && git reset --hard FETCH_HEAD
```
`FETCH_HEAD` is always written by `git fetch` and is unambiguous.

---

## Issue 3 — `data/documents/` empty on pod (60 SOP docs missing)

### Symptom
```
ls data/documents/*.docx | wc -l → 0
ModuleNotFoundError: No module named 'core.documents'   # (old code, git reset hadn't applied)
```

### Root Cause
Two compounding problems:
1. `data/documents/` was in `.gitignore` → never pushed, never pulled.
2. Issue 2 (git reset failure) meant new code (`core/documents.py`) wasn't on the pod either.

### What Was Tried (and failed)
- **SFTP via paramiko** → `SSHException: Channel closed` — RunPod gateway blocks the SFTP subsystem.
- **Committing docs to git** → worked for pull, but the repo is **public** and docs are sensitive internal SOPs → immediately reverted.

### Correct Solution — SCP upload
Use `scp` directly from your local machine to the pod via the SSH alias:
```bash
# Upload all 60 docs (run from project root)
scp -r "data/documents/" runpod2:/workspace/gemma-test/data/
```
This uses the same SSH key/host as the normal SSH session and is not blocked by the gateway.

> **Important:** Add this step to the deployment runbook before starting vLLM.
> The pod disk is ephemeral — re-upload after every pod restart.

### Permanent alternative
Store docs in a private S3 bucket / RunPod volume and add a download step to `start_api.sh`.

---

## Issue 4 — Sensitive data briefly exposed in public repo

### What Happened
Commits `7d78377` added 60 `.docx` SOP files to the public GitHub repo.
Commit `4bea39c` removed them from tracking via `git rm --cached`.

### Current Status
- Files are removed from `HEAD` and future commits ✅
- They **still exist in git history** at commit `7d78377` — anyone who clones before git history rewrite can access them.
- Local copies are safe (untracked, on disk only).

### Recommended Action (TODO)
Run a full history rewrite to purge the files from all commits:
```bash
# Requires git-filter-repo (pip install git-filter-repo)
git filter-repo --path data/documents/ --invert-paths
git push --force
```
⚠️ This rewrites history — all collaborators must re-clone afterward.

---

## Issue 5 — Old FETCH_HEAD from shell missing `python-docx`

### Symptom
```
ModuleNotFoundError: No module named 'docx'
```

### Fix
Add to `requirements.txt`:
```
python-docx==1.1.2
```
And run on pod:
```bash
pip install python-docx==1.1.2
```
Already committed in `931535a`.

---

## What IS Working

| Component | Status | Notes |
|-----------|--------|-------|
| vLLM 0.20.0 installed | ✅ | `/usr/local/lib/python3.11/dist-packages/vllm` |
| GemMaroc-27b-it downloaded | ✅ | 52GB at `/workspace/models/GemMaroc-27b-it` |
| FastAPI starts | ✅ | Confirmed `Uvicorn running on http://0.0.0.0:8000` |
| Auth (`/auth/login`) | ✅ | Returns `{"authenticated": true, "role": "user"}` with `user1234` |
| `/health` endpoint | ✅ | Returns `{"status":"ok"}` once vLLM is actually up |
| Web UI built | ✅ | `web_test/dist/` exists and served at `/` |
| BM25 doc retrieval (`core/documents.py`) | ✅ locally | Not yet active on pod (docs not uploaded) |
| SSH tunnel | ✅ | Standard: `-L 8000:localhost:8000 -L 8002:localhost:8002 runpod2` |

---

## Next Steps (in order)

1. **Update SSH tunnel** to also forward port 8002:
   ```bash
   ssh -L 8000:localhost:8000 -L 8002:localhost:8002 runpod2
   ```

2. **Upload SOP documents via SCP**:
   ```bash
   scp -r "data/documents/" runpod2:/workspace/gemma-test/data/
   ```

3. **On pod**: pull latest code and start services:
   ```bash
   cd /workspace/gemma-test
   git fetch origin main && git reset --hard FETCH_HEAD
   sed -i 's/\r//' scripts/*.sh && chmod +x scripts/*.sh
   pip install python-docx==1.1.2
   pkill -9 -f vllm; pkill -9 -f uvicorn
   sed -i 's|^VLLM_BASE_URL=.*|VLLM_BASE_URL=http://localhost:8002|' .env
   sed -i 's/^VLLM_MODEL_NAME=.*/VLLM_MODEL_NAME=gemmaroc/' .env
   mkdir -p logs
   nohup bash scripts/start_vllm.sh gemmaroc > logs/vllm_gemmaroc.log 2>&1 &
   nohup bash scripts/start_api.sh > logs/api.log 2>&1 &
   ```

4. **Verify**:
   ```bash
   curl http://localhost:8002/health        # vLLM
   curl http://localhost:8000/health        # FastAPI
   ```

5. **Browse** `http://localhost:8000` — password: `user1234`

6. **Purge git history** of the sensitive docs (see Issue 4).
