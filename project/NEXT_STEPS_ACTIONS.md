# Next steps — “Actions” beyond plain chat (tools, SQL, humans)

This doc is a **roadmap** for extending the SENDIT assistant from **read-only RAG** to **controlled actions** (e.g. run SQL, notify people, create tickets). Requirements will be refined later; use this as a checklist and architecture spine.

---

## 1. Which model target is MoE today?

`bash scripts/start_vllm.sh` model keys:

| Key | Local path | Role |
|-----|------------|------|
| **`gemma4`** | `gemma4-26b-it` | **Gemma 4 26B-IT — MoE** (what vLLM loads as `Gemma4ForConditionalGeneration`; **this is the production MoE stack**). |
| **`gemma`** | `gemma-3-27b-it` | Gemma 3 27B checkpoint (dense transformer family; not the Gemma 4 MoE path). |
| **`gemmaroc`** | `GemMaroc-27b-it` | Alternate Moroccan-tuned 27B-style checkpoint. |
| **`atlaschat`** | `Atlas-Chat-27B` | Alternate chat model. |

**Working setup** in recent runs: **`gemma4`** + **`VLLM_MODEL_NAME=gemma4-26b-it`** in `.env`. The others only work if the matching folder exists under `/workspace/models/`.

---

## 2. Goals for “actions”

- **Safe**: no arbitrary SQL or outbound comms without **policy + approvals + audit**.
- **Observable**: every tool call logged (who, when, inputs summary, result status).
- **Reversible where possible**: e.g. dry-run SQL, staged writes, idempotent APIs.

---

## 3. Suggested phases

### Phase A — Tool contract (backend)

1. Define a **small allow-listed tool set** (JSON schema per tool): e.g. `lookup_shipment`, `draft_email`, `run_readonly_sql`, `request_human_escalation`.
2. Add **FastAPI routes** or an internal **orchestrator** that:
   - Validates the model’s proposed tool call against schema.
   - Enforces **role** (user vs admin) and **environment** (dev/staging/prod).
3. **Do not** pipe raw model text into SQL or SMTP; only **structured** calls gated in code.

### Phase B — SQL (read vs write)

- **Read-only** first: dedicated DB user, statement/class allow-list, **row limits**, timeouts, no DDL.
- **Writes**: require **human confirmation** UI, **two-person** rule for sensitive ops, or **ticket queue** instead of direct `UPDATE`.
- Log **query hash + params** (never log secrets).

### Phase C — Contacting personnel

- Integrate with **email / Teams / Slack / internal queue** via existing org APIs.
- Model outputs **draft**; human sends, **or** auto-send only for **low-risk templates** with fixed bodies.
- Store **conversation id + escalation** in SQLite or CRM.

### Phase D — Frontend

- **Action cards**: “Proposed action” with Confirm / Reject.
- **Audit trail** view (admin): filters by user, tool, outcome.

### Phase E — Model layer

- Option A: **Structured output** (JSON tool calls) + parser validation.
- Option B: **Manual “continue”** flow already in `SYSTEM_PROMPT`; extend with **tool-result** messages in `messages` before next turn.

---

## 4. Security & compliance

- **Secrets**: only in `.env` / secret manager — **never** in git (see `.gitignore`).
- **PII**: minimize retention; align with DPO / internal policy.
- **Rate limits**: existing `/chat` limits; extend per-tool quotas.

---

## 5. Hooking to “GitHub Actions” (CI/CD)

- **Build**: `cd web_test && npm ci && npm run build`; ship `dist/` to pod or artefact store.
- **Deploy**: SSH or RunPod API — `git pull`, `pip install -r requirements.txt`, restart `start_all.sh` or `systemd`/tmux.
- **Smoke tests**: `scripts/test_pipeline.py` or curl `/health` + one authenticated `/chat`.
- **Secrets in CI**: `USER_SITE_PASSWORD` / `ADMIN_SITE_PASSWORD` as **GitHub Actions secrets**, injected into pod `.env` in deploy step — **not** stored in the repo.

---

## 6. Immediate ops reminder

- After changing `.env` passwords on the pod, **restart uvicorn** so `Settings()` reloads.
- Rebuild SPA if FastAPI serves `web_test/dist`: `npm run build` on the pod.
