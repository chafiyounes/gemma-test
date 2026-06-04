# Gemma-Test (SendBot) — User & Operator Guide

**Project:** Internal SENDIT customer-support chatbot  
**Repository:** [github.com/chafiyounes/gemma-test](https://github.com/chafiyounes/gemma-test)  
**Purpose of this document:** How the system works end-to-end and how to use, deploy, and maintain each component separately.

**Complete commit history:** [`CHANGELOG.md`](CHANGELOG.md) · **Documentation map:** [`COVERAGE_INDEX.md`](COVERAGE_INDEX.md)

---

## 1. What SendBot does

SendBot answers SENDIT staff questions using **internal SOPs and help articles**. It:

- Retrieves relevant documents (RAG) before answering
- Supports **French, Darija, English, and mixed** input
- Cites sources and can show **screenshots** for "where to click" questions
- Optionally shows **procedure flowcharts (logigrammes)** when asked
- Logs all interactions for admin review and feedback

It does **not** execute actions in SENDIT systems (no SQL, email, or ticket writes) — read-only chat for now.

---

## 2. Quick start by role

### 2.1 Staff user (chat only)

1. Open `http://<host>:8000` (or tunneled `http://localhost:8000`)
2. Log in with your **username + password**
3. Choose RAG scope if available: **Procedures**, **Help**, or **All**
4. Ask a question in any supported language
5. Click **Source:** on a reply to preview the original document
6. Use thumbs up/down for feedback

**Tip:** Start a **New chat** if the page shows stale history (transcripts live in browser `localStorage`).

---

### 2.2 Manager / administrator (admin console)

1. Open `http://<host>:8000/admin`
2. Log in (manager or administrator account)
3. Use tabs:
   - **Interactions** — review conversations, RAG metadata, feedback
   - **Documents** — upload, replace, organize corpus files
   - **Logigrammes** — create/edit procedure flowcharts (procedures only)
   - **Utilisateurs** — manage accounts (administrator only)
   - **Paramètres** — view RAG mode and env snapshot (administrator only)

---

### 2.3 Developer / operator (pod)

```bash
# On RunPod pod
cd /workspace/gemma-test
git fetch origin main && git reset --hard FETCH_HEAD
bash scripts/restart_api.sh          # API only (keeps vLLM loaded)

# From laptop (after git push)
python scripts/deploy_runner.py --skip-deps
```

---

## 3. System components — how each part works

### 3.1 vLLM inference server (port 8002)

**Role:** Loads the LLM on GPU; exposes OpenAI-compatible `/v1/chat/completions`.

**Start:**
```bash
bash scripts/start_vllm.sh gemma4     # production
bash scripts/start_vllm.sh gemmaroc   # alternate model
```

**Verify:**
```bash
curl -sS http://127.0.0.1:8002/v1/models
curl -sS http://127.0.0.1:8002/health
```

**Configure (`.env`):**
```env
VLLM_BASE_URL=http://localhost:8002
VLLM_MODEL_NAME=gemma4-26b-it
```

**When to restart:** Model change, vLLM flag change, OOM. Use `--restart all` in deploy_runner or restart tmux vLLM window.

**Logs:** `logs/vllm_*.log` or tmux vLLM pane.

---

### 3.2 FastAPI backend (port 8000)

**Role:** Auth, chat, RAG, admin API, static file serving, SQLite persistence.

**Start:**
```bash
bash scripts/start_api.sh
# Or full stack:
bash start_all.sh gemma4
```

**Verify:**
```bash
curl -sS http://127.0.0.1:8000/health
```

**Key endpoints:**

| Method | Path | Who | Purpose |
|--------|------|-----|---------|
| GET | `/health` | Public | API + model status |
| POST | `/auth/login` | Public | Session cookie |
| POST | `/chat` | User+ | Main chat |
| GET | `/categories` | User+ | List RAG categories |
| POST | `/feedback` | User+ | Thumbs up/down (returns 204) |
| GET | `/api/documents/preview` | User+ | Document preview modal |
| GET | `/api/rag-media/{path}` | User+ | Screenshot images in answers |
| GET | `/admin/interactions` | Manager+ | Interaction list |
| POST | `/admin/rag-reload` | Manager+ | Re-index corpus |
| POST | `/admin/git-refresh` | Admin | Pull + frontend build |
| GET/POST | `/api/admin/logigramme/*` | Manager+ | Logigramme CRUD |

**Restart after:** Code deploy, `.env` password change, corpus admin changes (rag-reload may suffice).

**Logs:** `logs/api.log`

---

### 3.3 Chat frontend (`web_test/`)

**Role:** React SPA for staff chat.

**Development:**
```bash
cd web_test
npm install
npm run dev          # http://localhost:5173
```

Set API URL in app (stored in `localStorage`) or use Vite proxy to `localhost:8000`.

**Production build:**
```bash
cd web_test && npm run build    # → dist/
```

FastAPI serves `web_test/dist/` at `/`. **Rebuild after every UI change** before users see updates.

**Theme:** Sun/moon toggle; stored as `localStorage.sendbot_theme` (`light` | `dark`).

**SSH tunnel (local dev against pod):**
```powershell
ssh -N -L 8000:localhost:8000 -L 8002:localhost:8002 <pod-alias>
# App API URL: http://localhost:8000
```

---

### 3.4 Admin console (`admin_site/`)

**Role:** Static HTML/JS for staff management — no separate build step.

**URL:** `http://<host>:8000/admin`

**After theme/CSS changes:**
1. Copy theme files: `bash scripts/sync_theme_assets.sh` (or manual copy to `admin_site/assets/`)
2. Bump `?v=` cache busters in `admin_site/index.html`
3. Hard-refresh browser (admin has no-cache headers)

**Document workflow:**
1. **Documents** tab → drag files or use file picker
2. Stage changes → review plan → **Apply**
3. API reloads DocStore automatically (or use **RAG reload**)

**Git refresh (administrator):** Pulls latest code + runs `npm run build` — does **not** replace corpus upload.

---

### 3.5 RAG document corpus

**Role:** Knowledge base for answers.

**Layout:**
```
data/documents/<category>/          ← authoritative source (.docx, .md, pdf)
data/documents_md/<category>/       ← generated MD (often pod-only)
data/logigrammes/procedures/*.mmd   ← flowchart sidecars
```

**Add documents — three ways:**

| Method | When to use |
|--------|-------------|
| Admin UI upload | Day-to-day additions by managers |
| scp / direct SSH | Bulk initial upload to pod |
| `python scripts/fetch_pod_tar.py` | Pull corpus from pod to local |

**Reload index after disk changes:**
- Admin → **RAG reload**, or
- `POST /admin/rag-reload`

**Audit a query:**
```bash
python scripts/rag_audit.py "texte de la question" procedures
```

**Default category:** Set `RAG_DEFAULT_CATEGORY=procedures` in `.env`.

---

### 3.6 SQLite interactions database

**Role:** Stores every chat turn, metadata, feedback.

**Path:** `data/interactions.db` (configurable via `INTERACTIONS_DB_PATH`)

**Admin uses it for:** Interaction list, detail view, RAG metadata inspection, feedback reports.

**Backup:** Copy the `.db` file while API is stopped or use SQLite backup commands.

---

### 3.7 Document preview (Source line)

**Role:** Let users view original `.docx` or cleaned Markdown when clicking **Source:** on a reply.

**Does not affect chat/RAG** — safe to iterate independently.

**Test after deploy:**
1. Send a chat message
2. Click **Source:** filename
3. Modal opens: **Word | Markdown | Logigramme** tabs

**Smoke script:** `bash scripts/pod_preview_smoke.sh`

---

### 3.8 Logigrammes (procedure flowcharts)

**Role:** Visual procedure diagrams in Mermaid format.

**Create (manager/admin):**
1. Admin → Documents → **Créer / Modifier logigramme**
2. **Générer** from procedure text
3. Edit Mermaid code; preview updates live
4. **Publier** when ready (drafts are private until publish)

**In chat:** Ask explicitly — *"Montre-moi le logigramme pour…"* — diagram appears below the text answer.

**Storage:**
- Published: `data/logigrammes/procedures/<stem>.mmd`
- Draft: `data/logigrammes/procedures/drafts/<username>/<stem>.mmd`

---

### 3.9 Feedback & liked-answer cache

**Feedback (`POST /feedback`):**
- Thumbs up / down on each assistant reply
- Dislike opens reason picker + optional comment
- Returns **204 No Content** — client must not parse JSON
- Stored in SQLite; visible in admin interaction detail

**Liked-answer cache:**
- When `LIKED_ANSWER_CACHE_ENABLED=true`, repeat identical questions may return a cached **liked** answer (skips vLLM)
- Dislike invalidates cache for that interaction
- Administrator can flush cache from **Paramètres** page

---

### 3.10 Corpus ingestion (outside admin UI)

| Task | Command / script |
|------|------------------|
| Scrape SENDIT help center | `python scrape_sendit.py` → `sendit_docs/` (then copy into `data/documents/help_md/`) |
| Export local DOCX → MD | `python scripts/export_sop_to_md.py` |
| Export DOCX → plain text | `python scripts/export_sop_to_txt.py` |
| Bulk upload to pod | `python scripts/upload_docs.py` or `upload_zip.py` |
| Pull corpus from pod | `python scripts/fetch_pod_tar.py` |
| Bootstrap help_md on pod | `bash scripts/materialize_help_md_from_git.sh` |
| Audit disk vs index | `python scripts/corpus_disk_vs_store.py` |

---

## 4. Chat modes explained

### 4.1 Classic RAG (default)

- Retrieves documents via BM25 or full-category inject
- Single vLLM completion with SYSTEM_PROMPT + documents + history
- Best for single-category questions (e.g. `procedures` only)

**Preflight (no LLM):** Greetings, help requests, and off-topic messages get instant fixed replies (`core/chat_policy.py`). **Continuation:** saying *suite* / *continue* reuses your last question for retrieval.

### 4.2 Agentic RAG (optional)

Enable in `.env`:
```env
AGENTIC_RAG_ENABLED=true
AGENTIC_RAG_ON_MULTI_SCOPE=true
```

- **Phase 1:** Model picks documents from catalog via `request_documents` tool
- **Phase 2:** Answers using full selected document bodies
- Auto-used for **All categories** scope when enabled
- Requires Gemma 4 vLLM with tool flags

**Test on pod:**
```bash
export ADMIN_PASSWORD=$(grep ^ADMIN_SITE_PASSWORD= .env | cut -d= -f2-)
python scripts/test_agentic_rag_pod.py
```

---

## 5. Configuration reference

Copy `.env.example` → `.env` on pod and fill in:

| Variable | Description |
|----------|-------------|
| `USER_SITE_PASSWORD` | Default chat login (or use seeded users) |
| `ADMIN_SITE_PASSWORD` | Admin login |
| `SESSION_SECRET_KEY` | Cookie signing — long random string |
| `VLLM_BASE_URL` | `http://localhost:8002` |
| `VLLM_MODEL_NAME` | Must match vLLM served id |
| `RAG_INJECT_MAX_CHARS` | Max document context (default ~22000) |
| `RAG_DEFAULT_CATEGORY` | Default when client omits scope |
| `MAX_NEW_TOKENS` | Answer length limit (2048 typical) |
| `AGENTIC_RAG_ENABLED` | `true`/`false` |
| `LIKED_ANSWER_CACHE_ENABLED` | Cache liked answers (default `true`) |
| `RATE_LIMIT_MAX_REQUESTS` | Chat requests per window (default 30) |
| `RATE_LIMIT_WINDOW_SECONDS` | Rate limit window (default 60) |
| `API_EXPOSE_ERROR_DETAIL` | Debug 500s — **off in production** |

**User management without redeploy:**
```bash
bash scripts/manage_users.sh list
bash scripts/manage_users.sh add username password manager
```

---

## 6. Deployment workflows

### 6.1 Code-only change (most common)

```powershell
# Local: commit + push
git push origin main

# Laptop → pod
python scripts/deploy_runner.py --skip-deps
```

This: git pull on pod, `npm run build`, restart API. vLLM stays loaded.

---

### 6.2 Full stack restart (model / vLLM flags)

```powershell
python scripts/deploy_runner.py --skip-deps --restart all
```

Or on pod:
```bash
bash start_all.sh gemma4
```

---

### 6.3 Fresh pod setup

```bash
cd /workspace
git clone https://github.com/chafiyounes/gemma-test.git
cd gemma-test
cp .env.example .env    # edit values
pip install -r requirements.txt
pip install -r requirements-api.txt
# Upload corpus (scp or admin)
cd web_test && npm install && npm run build && cd ..
bash start_all.sh gemma4
```

See `docs/runbook_runpod_quick_start.md` for troubleshooting.

---

### 6.4 Windows-specific

After pulling shell scripts on pod:
```bash
sed -i 's/\r//' scripts/*.sh start_all.sh
chmod +x scripts/*.sh start_all.sh
```

---

## 7. Health checks & monitoring

```bash
# API
curl -sS http://127.0.0.1:8000/health

# vLLM
curl -sS http://127.0.0.1:8002/v1/models

# Logs
tail -f logs/api.log logs/vllm_*.log

# Remote via gateway
python scripts/pod_cmd.py "curl -s http://127.0.0.1:8000/health"
```

**Degraded health** usually means vLLM is down or still loading — check GPU memory and vLLM log.

---

## 8. Troubleshooting guide

| Problem | What to check | Fix |
|---------|---------------|-----|
| Blank chat page | `web_test/dist/index.html` exists? | `npm run build` |
| 500 on admin documents | `logs/api.log` traceback | See `ADMIN_INTERNAL_SERVER_ERROR.md` |
| No sources in answers | Corpus on pod? RAG scope? | Upload docs; `rag-reload`; check `rag_audit.py` |
| Answer cut off mid-sentence | `finish_reason=length` | Continuation enabled; raise `MAX_NEW_TOKENS` |
| vLLM 400 context error | Prompt too large | Lower `RAG_INJECT_MAX_CHARS` |
| Agentic returns empty tools | vLLM tool flags | Check `start_vllm.sh gemma4` flags |
| Preview 404 | Title vs filename mismatch | Fuzzy resolve should handle; check file on disk |
| Theme looks wrong (Brave) | Browser forced colors | Disable in Brave settings |
| SSH command fails | Gateway PTY | Use `pod_cmd.py` or direct SSH |

---

## 9. Scripts reference

| Script | Use |
|--------|-----|
| `scripts/deploy_runner.py` | Push-to-pod deploy (git + build + restart) |
| `scripts/pod_cmd.py` | Run single command on pod via gateway |
| `scripts/fetch_pod_tar.py` | Download corpus from pod |
| `scripts/restart_api.sh` | Restart API in tmux |
| `scripts/start_vllm.sh` | Start vLLM with model key |
| `scripts/build_web.sh` | Build chat frontend |
| `scripts/rag_audit.py` | Debug retrieval vs missing topic |
| `scripts/test_agentic_rag_pod.py` | Agentic integration test |
| `scripts/test_rag_inject_greedy.py` | Greedy inject regression |
| `scripts/manage_users.sh` | CLI user management |
| `scripts/materialize_help_md_from_git.sh` | Bootstrap help_md on pod |
| `scripts/export_sop_to_md.py` | Batch DOCX → Markdown |
| `scripts/export_sop_to_txt.py` | Batch DOCX → plain text |
| `scripts/upload_docs.py` | Upload corpus to pod |
| `scripts/runpod_recycle_pod.py` | Recycle RunPod when GPU VRAM stuck |
| `scripts/manim_gemma_architecture.py` | Render architecture Manim videos |
| `scripts/eval_logigramme_formats.py` | Logigramme format evaluation |
| `scripts/test_conversation_intent.py` | Preflight intent unit tests |
| `scripts/remote_post_deploy_verify.py` | Post-deploy smoke on pod |
| `scrape_sendit.py` | Scrape help.sendit.ma → `sendit_docs/` |
| `scripts/check_health.py` | Local health check |
| `scripts/ssh_runpod_diagnostics.py` | Full pod diagnostic bundle |

---

## 10. Testing checklist

### After any deploy
- [ ] `GET /health` returns `"status":"ok"`
- [ ] Login to chat works
- [ ] Send test question → answer with Source line
- [ ] Admin interactions list loads

### After RAG/corpus change
- [ ] `POST /admin/rag-reload` or apply-plan reload
- [ ] `python scripts/rag_audit.py "<query>" procedures` shows hits
- [ ] Admin interaction detail shows `context_chars` > 0

### After frontend change
- [ ] `npm run build` completed
- [ ] Hard-refresh browser
- [ ] Theme toggle works

### After agentic change
- [ ] `python scripts/test_agentic_rag_pod.py` passes
- [ ] Metadata shows `tool_rounds` > 0 for multi-doc queries

---

## 11. Security notes (current posture)

- Passwords in `.env` — never commit real secrets
- Corpus gitignored — upload to pod separately
- Roles: user < manager < administrator
- `API_EXPOSE_ERROR_DETAIL` exposes internals — debug only
- Full security hardening (rotation, secret manager) planned but not priority (see ROADMAP)

---

## 12. Glossary

| Term | Meaning |
|------|---------|
| **RAG** | Retrieval-Augmented Generation — inject docs before LLM answer |
| **DocStore** | In-memory index of corpus + BM25 scorer |
| **SOP** | Standard Operating Procedure (SendIT internal doc) |
| **Logigramme** | Flowchart diagram (Mermaid) for a procedure |
| **Agentic RAG** | Two-phase: model picks docs via tool, then answers |
| **Scope** | Which categories to search: procedures, help_md, all |
| **Sidecar** | Separate file (`.mmd`) attached to a procedure |
| **Preflight** | Fixed reply without LLM for greetings / off-topic |
| **Liked cache** | SQLite cache of answers user marked helpful |
| **Pod** | RunPod GPU cloud instance running the stack |

---

## 13. Related documentation

| Document | When to read |
|----------|--------------|
| `project/SUMMARY_ARCHITECTURE.md` | System design, modules, data flow |
| `project/SUMMARY_BUGS_AND_CHANGES.md` | History of problems and fixes |
| `project/CHANGELOG.md` | All 147 commits (complete audit trail) |
| `project/COVERAGE_INDEX.md` | What is documented where; gaps |
| `project/ARCHITECTURE.md` | Detailed technical architecture |
| `project/DEPLOYMENT.md` | SSH nuances, deploy pitfalls |
| `project/DATA_LAYOUT.md` | Where corpus files live |
| `project/DOCUMENT_PREVIEW.md` | Source modal subsystem |
| `project/LOGIGRAMME.md` | Flowchart feature details |
| `project/DESIGN_SYSTEM.md` | Theme tokens and maintenance |
| `project/ROADMAP.md` | Product priorities and future work |
| `docs/runbook_runpod_quick_start.md` | Pod quick start runbook |

---

## 14. Repository & contacts

- **GitHub:** [github.com/chafiyounes/gemma-test](https://github.com/chafiyounes/gemma-test)
- **Stack:** FastAPI + vLLM + React + SQLite on RunPod (2× A40)
- **Primary model:** Gemma 4 26B-IT MoE via vLLM

For architecture decisions and incident history, see the companion summary documents in `project/`.
