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

### 3.1 UI theme redesign (in progress — May 2026)

**Goal:** Shared **light** (default) / **dark** design for **chat** (`web_test`) and **admin** (`admin_site`), SENDIT copper accent only, manual sun/moon toggle (`localStorage.sendbot_theme`). Design-only — no RAG/API changes.

| Area | Status | Notes |
|------|--------|--------|
| Shared tokens | Done | `shared/theme/theme-light.css`, `theme-dark.css`, `theme-base.css`; logic in `theme-core.js` / `theme-sync.js` |
| Chat (`web_test`) | Mostly OK | Light/dark toggle, surfaces aligned with admin; file-swap stylesheets + static `<link>` in `index.html` |
| Document preview modal | Done | Word tab stays paper-white; modal chrome follows theme — see [`DOCUMENT_PREVIEW.md`](DOCUMENT_PREVIEW.md) |
| Admin (`admin_site`) | **Fixed (May 2026)** | Hardcoded dark-era colors migrated to `var(--*)` tokens in `admin.css`; toggle icon updates on inline boot + `DOMContentLoaded`. Hard-refresh `/admin` after deploy. |
| Browser forced colors | Partial | File-swap + `color-scheme: only light\|dark` helps Chrome; Brave “Colors for all websites” can still override — user must disable in browser settings |

**Recent commits (theme):** `8aaa11f` (initial light/dark), `83a1417` (OS decouple), `4113d44` (Brave hardening), `cda102c` (file-swap), `b520258` (unify toggle), `5bc3dec` (static admin CSS load order — **admin still reported broken**).

**Next steps (admin):** Optional UX polish — “Charger plus” button if infinite scroll is unreliable; persist list scroll position when returning from detail.

### 3.2 Admin performance (May 2026)

- List endpoint: `GET /admin/interactions?summary=1&limit=30&offset=N` — lightweight rows (no `response`/`metadata`).
- Frontend: infinite scroll, debounced search (300ms), lazy RAG reconstruction (`?reconstruct_rag=1` on demand).
- Result count: `"30 sur 847"` while paginating.

**Docs:** [`DESIGN_SYSTEM.md`](DESIGN_SYSTEM.md)

---

## 3.3 Logigrammes (May 2026)

Procedure → Mermaid flowchart via Gemma. **Procedures only** — admin/manager modal, sidecar storage, preview tab, RAG merge. Normal chat unchanged. See [`LOGIGRAMME.md`](LOGIGRAMME.md).

| Piece | Status |
|-------|--------|
| `core/logigramme_llm.py` | Done — Mermaid generation |
| `core/logigrammes_store.py` | Done — `data/logigrammes/procedures/<stem>.mmd` |
| `core/logigramme_service.py` | Done — admin generate/refine/save |
| Admin modal (manager + admin) | Done |
| Document preview Logigramme tab | Done |
| RAG merge at index time | Done |
| Classic chat logigramme intent | **On** (explicit keywords only; see [`LOGIGRAMME.md`](LOGIGRAMME.md)) |
| Chat message Mermaid renderer | **Off** (preview only) |

**Next:** Manual fidelity review on saved sidecars; tune refine prompts if branches are missing.

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
| `shared/theme/` | Light/dark CSS + `theme-core.js` (chat/admin theme) |
| `core/logigramme_llm.py` | Mermaid logigramme generation from procedures |
| `project/LOGIGRAMME.md` | Logigramme prototype, chat triggers, quality checklist |
