# Deployment — gemma-test (RunPod + local)

**See also:** [`ARCHITECTURE.md`](ARCHITECTURE.md) (RAG, agentic, modules), [`ROADMAP.md`](ROADMAP.md) (product focus, future actions).

---

## 1. What runs where

| Service | Port | Notes |
|---------|------|--------|
| **vLLM** | **8002** | `scripts/start_vllm.sh` (preferred) |
| **FastAPI** | **8000** | Serves API + `web_test/dist` if built |
| **Vite dev** | 5173 | Local only |

**RAG data:** prefer `data/documents_md/`; corpus may live **only on the pod** (not in git). **SQLite:** `data/interactions.db`.

---

## 2. SSH: gateway vs direct (important)

### RunPod gateway (`ssh.runpod.io`)

- Many **non-interactive** patterns fail: `ssh user@ssh.runpod.io "command"` often errors (**PTY required**).
- **`scp` / SFTP** through the gateway frequently fails (**subsystem / channel closed**).
- **What works:** interactive SSH, or **Paramiko + PTY** from the repo:
  - `python scripts/pod_cmd.py "cd /workspace/gemma-test && git pull origin main"`
  - `python scripts/deploy_runner.py` (uses the gateway user/host **inside the script** — edit `HOST`/`USER` there if your pod identity changes).

### Direct pod SSH (if RunPod exposes it)

Example pattern that often works for **one-shot** commands (no PTY issues):

```bash
ssh -o BatchMode=yes -p <PORT> -i ~/.ssh/id_ed25519 root@<PUBLIC_IP> "cd /workspace/gemma-test && git pull origin main && bash scripts/restart_api.sh"
```

Ports and IPs **change** when the pod is recreated — update your notes/SSH config; do not treat historical IPs as permanent.

**Windows key path:** `-i "$env:USERPROFILE\.ssh\id_ed25519"` (PowerShell).

---

## 3. Deploy / refresh code

### One-click (from your laptop; gateway + PTY)

```powershell
cd "...\gemma-test"
python scripts/deploy_runner.py                    # full: deps + git + npm build + restart
python scripts/deploy_runner.py --skip-deps        # faster: pull, build, restart API only (default)
python scripts/deploy_runner.py --skip-deps --restart all   # tmux + start_all (reloads vLLM)
```

`deploy_runner` ends with **`git reset --hard FETCH_HEAD`** on `main` — destructive to local changes on the pod under that clone.

### Minimal API redeploy (keep vLLM loaded)

On the pod:

```bash
cd /workspace/gemma-test
git pull origin main
bash scripts/restart_api.sh    # requires existing tmux session `gemma-test` from start_all
```

Or admin: **`POST /admin/git-refresh`** (pull + frontend build + DocStore reload — see API).

After **`pip` / dependency** changes, restart API (or full stack) as appropriate.

### Frontend

After **every** `git pull` that touches the chat UI, rebuild the SPA (otherwise the browser may still get an old `web_test/dist`):

```bash
cd /workspace/gemma-test && bash scripts/build_web.sh
```

Or use **Admin → Git refresh**: it now runs **`npm install` + `npm run build`** in `web_test` after pull, then reloads the RAG index. **Still restart the API** (`bash scripts/restart_api.sh`) so uvicorn picks up fresh static files if needed.

Fail closed: `web_test/dist/index.html` must exist if the API serves the SPA.

### Line endings (Windows clones)

```bash
sed -i 's/\r//' scripts/*.sh start_all.sh
chmod +x scripts/*.sh start_all.sh
```

---

## 4. First-time / full stack on pod

```bash
cd /workspace/gemma-test
git pull origin main
python3 -m pip install -r requirements.txt
python3 -m pip install -r requirements-api.txt   # PDF RAG, etc.
cd web_test && npm install && npm run build && cd ..
bash start_all.sh gemma4      # tmux: vllm window + api window
```

**`.env`** on pod: `VLLM_BASE_URL`, `VLLM_MODEL_NAME`, passwords, `SESSION_SECRET_KEY`, optional `AGENTIC_RAG_ENABLED=true`. See **`.env.example`**.

---

## 5. Local access (tunnel)

```powershell
ssh -L 8000:localhost:8000 -L 8002:localhost:8002 <user>@<host>
# API http://localhost:8000   vLLM http://localhost:8002
```

---

## 6. Health checks

```bash
curl -sS http://127.0.0.1:8000/health
curl -sS http://127.0.0.1:8002/v1/models   # JSON = inference up
```

From Windows via gateway:

```powershell
python scripts/pod_cmd.py "curl -s http://127.0.0.1:8000/health"
```

---

## 7. Model keys (`start_vllm.sh`)

| Key | Typical path under `/workspace/models/` |
|-----|----------------------------------------|
| `gemma4` | `gemma4-26b-it` (production MoE) |
| `gemma` | `gemma-3-27b-it` |
| `gemmaroc` | `GemMaroc-27b-it` |
| `atlaschat` | `Atlas-Chat-27B` |

`.env` **`VLLM_MODEL_NAME`** must match the **served** model id.

---

## 8. Agentic RAG on the pod

1. `.env`: `AGENTIC_RAG_ENABLED=true` (and vLLM with Gemma 4 **tool** flags — see `ARCHITECTURE.md`).
2. Restart API after `.env` changes.
3. Integration test (set admin password from `.env`):

   ```bash
   export ADMIN_PASSWORD=$(grep ^ADMIN_SITE_PASSWORD= .env | cut -d= -f2-)
   export USER_PASSWORD=$(grep ^USER_SITE_PASSWORD= .env | cut -d= -f2-)
   python scripts/test_agentic_rag_pod.py
   ```

Optional map/e5 scripts are **not** required for the **catalog + request_documents** two-phase path.

---

## 9. Pitfalls we hit (checklist)

| Issue | Cause / fix |
|--------|-------------|
| SSH **PTY** error | Use **`pod_cmd.py`**, **`deploy_runner.py`**, or **direct** root SSH with port |
| **`scp`/SFTP** fails on gateway | Use **`git push` + `git pull`** on pod, or direct SSH if available |
| API **ImportError** on agentic (`_best_window_for_query`) | **`core/documents.py` on branch must match** `core/agentic_rag.py` imports — pull latest `main` |
| **`tool_rounds=0`** in metadata while tools ran | Fixed in app: answer phase must **not** overwrite router **`tool_rounds`**; use current `main` |
| API down after **`restart_api.sh`** | Wait for tmux **api** pane to bind **8000**; read `logs/api.log` |
| Blank SPA | `npm run build` in `web_test` |
| vLLM OOM | Lower `VLLM_MAX_MODEL_LEN` / `VLLM_GPU_MEMORY_UTILIZATION` in `start_vllm.sh` |

---

## 10. Verifying “is it deployed?”

On the pod:

```bash
cd /workspace/gemma-test && git log -1 --oneline
curl -sS http://127.0.0.1:8000/health
```

Compare commit to your **`origin/main`**.

---

## 11. Admin + corpus debugging

- **Admin UI:** `http://<host>:8000/admin` (admin cookie).
- **Generic 500 / “Internal server error” on documents:** see [`ADMIN_INTERNAL_SERVER_ERROR.md`](ADMIN_INTERNAL_SERVER_ERROR.md) (logs, `API_EXPOSE_ERROR_DETAIL`, overview/RAG reload pitfalls).
- **`metadata.rag`** on interactions: `context_chars`, `documents_in_prompt`, `fetch_count` (agentic), `tool_rounds`, `mode` (e.g. `agentic_rag_two_phase`).
- **`scripts/rag_audit.py`** on the machine that holds **`data/documents*`**: disambiguates “missing from corpus” vs “retrieval/model issue”.

---

## 12. Browser note

Chat transcripts live in **`localStorage`**; refresh can replay old text — use **New chat** if you suspect stale UI state.

---

## 13. `push_to_runpod.py`

Optional Paramiko upload script; **SFTP is often blocked** on `ssh.runpod.io`. Prefer **git** for deploy.
