# Roadmap & product context — gemma-test

**Companion docs:** [`ARCHITECTURE.md`](ARCHITECTURE.md) (how it works), [`DATA_LAYOUT.md`](DATA_LAYOUT.md) (document folders, pod vs git), [`DEPLOYMENT.md`](DEPLOYMENT.md) (SSH, pod, deploy).

Security hardening (strong passwords, secret rotation) is **explicitly secondary for now**; focus is **answer quality** and **RAG transparency**.

---

## 1. Near-term product goals

1. **Context use:** The model must follow injected SOPs (**DOCUMENTS DE RÉFÉRENCE**) even when users write **Darija / English / mixed**.
2. **No silent void:** If no document context was injected, **`metadata.rag`** (and admin) should make that obvious (`context_chars`, `documents_in_prompt`, `note`, category).
3. **Default category:** If the client omits `category`, the API uses **`RAG_DEFAULT_CATEGORY`** when that folder exists, else first category alphabetically (`app_config/settings.py`).

---

## 2. Auditing “answer not in corpus”

Git may omit `.docx`/`.txt`; data often lives **on the pod** only. On the machine with the files:

```bash
cd /workspace/gemma-test
python scripts/rag_audit.py "your query snippet" procedures
```

If theme counters are all **0**, the topic may be absent; if **> 0**, check admin RAG preview and **`RAG_INJECT_MAX_CHARS`**.

---

## 3. Admin console

- **`/admin`** — same origin as API; static assets under **`/admin-static/`**.
- Useful for **feedbacks**, filters, conversation/thread views, **rag** metadata per turn.

---

## 4. Inference targets (which “Gemma” is MoE?)

| `start_vllm.sh` key | Role |
|---------------------|------|
| **`gemma4`** | **Gemma 4 26B-IT MoE** — primary production stack with vLLM |
| **`gemma`** | Gemma 3 27B-style dense (not Gemma 4 MoE path) |
| **`gemmaroc`** | Moroccan-tuned alternate |
| **`atlaschat`** | Alternate chat model |

Checkpoints must exist under **`/workspace/models/`**. Typical `.env`: **`VLLM_MODEL_NAME=gemma4-26b-it`** with **`gemma4`**.

---

## 5. Beyond read-only chat (“actions”) — phased spine

Goals: **safe** (policy + approvals + audit), **observable** tool logging, **reversible** flows where possible.

| Phase | Direction |
|-------|-----------|
| **A — Tool contract** | Small allow-listed tools (JSON schema); validate in FastAPI; enforce role + environment; **never** pipe raw model text into SQL/email |
| **B — SQL** | Read-only first (scoped user, allow-list, row limits); writes need human confirm or ticket queue |
| **C — Comms** | Draft-only or low-risk templates; integrate email/Teams/Slack/queue APIs |
| **D — UI** | Action cards (Confirm/Reject); admin audit trail |
| **E — Model** | Structured tool JSON + validation; or extend continue/tool-result message pattern |

**Compliance sketch:** secrets only in `.env`/secret manager; minimal PII retention; rate limits extended per-tool if needed.

---

## 6. CI/CD (later)

- Build: `cd web_test && npm ci && npm run build`
- Deploy: `git pull`, `pip install -r requirements.txt`, restart tmux API or full stack
- Smoke: `/health` + authenticated `/chat`
- GitHub Actions secrets for pod `.env` — not committed

---

## 7. Ops reminders

- After changing **`.env` passwords** on the pod, **restart uvicorn** so `Settings()` reloads.
- After **frontend** changes, **`npm run build`** if FastAPI serves `dist/`.

---

## 8. Key code pointers

| File | Role |
|------|------|
| `core/llm.py` | System prompt, RAG assembly, agentic orchestration |
| `core/documents.py` | DocStore, BM25, inject helpers |
| `core/agentic_rag.py` | Catalog, router tools, formatting |
| `api/main.py` | `/chat`, category resolution, admin |
| `core/persistence.py` | SQLite shape for admin |
| `project/DOCUMENT_PREVIEW.md` | **Source:** click → modal (`.docx` / MD); isolated from `/chat` |
| `core/document_preview.py` | Preview API resolve + trailing-link strip (display only) |
| `admin_site/` | Admin static UI |
