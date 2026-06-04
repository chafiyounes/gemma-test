# Gemma-Test (SendBot) — Bugs, Glitches & Changes

**Project:** Internal SENDIT customer-support chatbot  
**Repository:** [github.com/chafiyounes/gemma-test](https://github.com/chafiyounes/gemma-test)  
**Purpose of this document:** Chronological record of problems encountered, root causes, fixes, and major feature deliveries — suitable for reports, postmortems, and presentations.

**Complete commit history:** [`CHANGELOG.md`](CHANGELOG.md) · **Documentation map:** [`COVERAGE_INDEX.md`](COVERAGE_INDEX.md)

---

## 1. Timeline at a glance

| Period | Focus |
|--------|-------|
| **Apr 2026 — Initial deploy** | RunPod pod setup, vLLM port conflict, corpus upload, sensitive data incident |
| **Apr–May 2026 — RAG foundation** | BM25 retrieval, category scope, context budget tuning, Darija/EN hints |
| **May 2026 — Agentic RAG** | Two-phase catalog router, Gemma 4 tool use, metadata fixes |
| **May 2026 — Admin platform** | Document manager, role-based auth, resilient overview, git vs RAG controls |
| **May 2026 — UX & preview** | Document preview modal, shared light/dark theme, admin performance |
| **May 2026 — Logigrammes** | Mermaid flowcharts, draft/publish workflow, chat explicit intent |
| **May 2026 — Polish** | Continuation/repair tuning, greeting preflight, administrator settings page |

**Audit trail:** Every commit is listed in [`CHANGELOG.md`](CHANGELOG.md). Documentation map: [`COVERAGE_INDEX.md`](COVERAGE_INDEX.md).

---

## 2. Infrastructure & deployment issues

### 2.1 vLLM port 8001 conflict (Apr 2026)

| | |
|---|---|
| **Symptom** | vLLM crashed with `OSError: [Errno 98] Address already in use` on port 8001 |
| **Root cause** | RunPod exposes a **sidecar service on 8001** that responds 200 to `/health` but 405 on `/v1/chat/completions` — not vLLM |
| **Fix** | Moved vLLM to **port 8002** in `scripts/start_vllm.sh`; updated `VLLM_BASE_URL` and SSH tunnel (`-L 8002:localhost:8002`) |
| **Commit** | `a0187b7` |

---

### 2.2 RunPod gateway SSH / SFTP limitations

| | |
|---|---|
| **Symptom** | `ssh user@ssh.runpod.io "command"` fails (PTY required); `scp`/SFTP returns "Channel closed" |
| **Root cause** | Gateway restricts non-interactive exec and SFTP subsystem |
| **Fix** | Repo helpers with Paramiko + PTY: `scripts/pod_cmd.py`, `scripts/deploy_runner.py`, `scripts/fetch_pod_tar.py` (base64 stream for corpus download) |
| **Workaround** | Prefer **git push + git pull** on pod; direct root SSH when RunPod exposes IP:port |
| **Commit** | `03861c1`, corpus fetch documented in `DATA_LAYOUT.md` |

---

### 2.3 Git reset failure on pod

| | |
|---|---|
| **Symptom** | `fatal: ambiguous argument 'origin/main': unknown revision` |
| **Root cause** | Shallow clone without local `origin/main` ref |
| **Fix** | `git fetch origin main && git reset --hard FETCH_HEAD` in deploy scripts |
| **Commit** | Deploy script updates (see `deployment_issues_2026-04-28.md`) |

---

### 2.8 GPU VRAM stuck / pod recycle

| | |
|---|---|
| **Symptom** | vLLM preflight fails — insufficient free VRAM; ConnectError on restart |
| **Root cause** | Stale GPU processes after crash; RunPod GPU not released |
| **Fix** | VRAM reclaim before mem check; `scripts/runpod_recycle_pod.py` (RunPod REST); manual `pkill` + tmux restart |
| **Commits** | `d289fb5`, `d45256c` |

---

### 2.9 SGLang experiment (abandoned)

| | |
|---|---|
| **Symptom** | Evaluated SGLang as alternate inference server |
| **Outcome** | Not adopted; vLLM remains production path. Script lives in `artifacts/pod_install_sglang.py` (diagnostic only) |
| **Documented in** | `COVERAGE_INDEX.md` — not a production subsystem |

---

### 2.4 Empty corpus on pod / missing RAG

| | |
|---|---|
| **Symptom** | `data/documents/` empty after pod restart; RAG returns no context |
| **Root cause** | Corpus in `.gitignore`; pod disk is **ephemeral** |
| **Fix** | Upload via scp/direct SSH, admin UI uploads, or `fetch_pod_tar.py`; `materialize_help_md_from_git.sh` for help_md stub |
| **Related** | `932a157` — DocStore fallback when MD/TXT index zero docs; `186050e` — help_md bootstrap |

---

### 2.5 Sensitive SOPs briefly in public GitHub

| | |
|---|---|
| **Symptom** | 60 `.docx` SOP files committed to public repo |
| **Root cause** | Attempt to sync corpus via git when scp failed |
| **Fix** | `git rm --cached` + enforce `.gitignore` on `data/documents/` |
| **Status** | Removed from HEAD; **still in git history** at commit `7d78377` — history rewrite recommended if needed |
| **Commits** | `7d78377` (added), `4bea39c` (removed) |

---

### 2.6 Windows line endings on pod

| | |
|---|---|
| **Symptom** | Shell scripts fail with `$'\r': command not found` |
| **Fix** | `sed -i 's/\r//' scripts/*.sh start_all.sh && chmod +x scripts/*.sh` after pull |

---

### 2.7 GPU misdetection / phantom GPU (RunPod)

| | |
|---|---|
| **Symptom** | Two GPUs in `nvidia-smi` but CUDA context fails on one; vLLM OOM |
| **Root cause** | RunPod can expose inaccessible GPU index |
| **Fix** | `CUDA_VISIBLE_DEVICES=1` (or healthy index) in `start_vllm.sh`; `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` |
| **Commits** | `7f23e2c`, `9eaffda`, runbook in `docs/runbook_runpod_quick_start.md` |

---

### 2.8 Windows Unicode filename normalization

| | |
|---|---|
| **Symptom** | Accents stripped in filenames when extracting pod tar on Windows |
| **Fix** | Documented; extract from Linux/WSL for exact names; `.docx` contents unaffected |
| **Commit** | `78cb441` |

---

### 2.9 GPU VRAM stuck / pod recycle

| | |
|---|---|
| **Symptom** | vLLM preflight fails — insufficient free VRAM; ConnectError on restart |
| **Root cause** | Stale GPU processes after crash; RunPod GPU not released |
| **Fix** | VRAM reclaim before mem check; `scripts/runpod_recycle_pod.py` (RunPod REST); manual `pkill` + tmux restart |
| **Commits** | `d289fb5`, `d45256c` |

---

### 2.10 SGLang experiment (abandoned)

| | |
|---|---|
| **Symptom** | Evaluated SGLang as alternate inference server |
| **Outcome** | Not adopted; vLLM remains production path. Script: `artifacts/pod_install_sglang.py` (diagnostic only) |

---

## 3. Inference & model stability issues

### 3.1 vLLM NaN / CUDA assert / instability

| | |
|---|---|
| **Symptom** | vLLM crashes, NaN errors, CUDA asserts with Gemma 4 |
| **Mitigations tried** | Switched to Transformers fallback; Gemma 3 27B stability; bfloat16/float16 tuning; greedy decoding; reduced context |
| **Resolution** | Returned to **vLLM 0.19+** with Gemma 4 26B MoE, TP=2, tuned `max-model-len` |
| **Commits** | `c5c30b9` → `1274a9d` (evolution chain) |

---

### 3.2 Context length 400 errors from vLLM

| | |
|---|---|
| **Symptom** | vLLM returns 400 when prompt + max_tokens exceeds context window |
| **Fix** | Auto-retry with reduced `max_tokens`; align `RAG_INJECT_MAX_CHARS` with `LLM_MAX_CONTEXT_TOKENS` and vLLM `--max-model-len` |
| **Commits** | `56a0341`, `43205c2`, `53566f9`, `3cdadf6`, `2b6d2d5` |

---

### 3.3 Truncated / mid-answer cutoffs

| | |
|---|---|
| **Symptom** | Answers stop mid-sentence (`finish_reason=length`) |
| **Fix** | vLLM continuation rounds (`VLLM_MAX_CONTINUE_ROUNDS`); raised `MAX_NEW_TOKENS` to 2048; tighter RAG inject floor |
| **Commits** | `1c10db7`, `13a6afd`, `f8e5de8` |

---

### 3.4 Gemma 4 tool use misconfiguration (agentic)

| | |
|---|---|
| **Symptom** | Agentic router completes without `tool_calls`; `tool_rounds=0` in metadata |
| **Fix** | vLLM flags: `--enable-auto-tool-choice`, `--tool-call-parser gemma4`; forced `tool_choice` on first router round; answer phase must not overwrite `tool_rounds` |
| **Commits** | `52d74a7`, `ae0e293`, `ed51611` |

---

### 3.5 Missing `_best_window_for_query` import crash

| | |
|---|---|
| **Symptom** | API ImportError on agentic path after partial deploy |
| **Fix** | Ensure `core/documents.py` and `core/agentic_rag.py` deployed together |
| **Commit** | `9b76f22` |

---

### 3.6 Transformers ↔ vLLM oscillation (May 2026)

| | |
|---|---|
| **Symptom** | Gemma 4 NaN/CUDA asserts on vLLM; switched to Transformers + Gemma 3 for stability |
| **Timeline** | `c5c30b9` Transformers fallback → `26ba350` Gemma 3 27B → `1274a9d` back to Gemma 4 on vLLM 0.19 |
| **Lessons** | `use_fast=False` tokenizer; `CUDA_VISIBLE_DEVICES`; context limits must match RAG inject |

---

## 4. RAG quality & retrieval issues

### 4.1 Model ignores injected documents

| | |
|---|---|
| **Symptom** | Model answers from general knowledge despite large inject |
| **Fixes** | Stronger SYSTEM_PROMPT; RAG repair turn when model claims absent; `metadata.rag` transparency; Darija/EN BM25 hints; adjacent SOP synthesis prompt |
| **Commits** | `dd8e5fc`, `4221a12`, `3227a5f`, `96281a4` |

---

### 4.2 RAG inject exceeding vLLM context

| | |
|---|---|
| **Symptom** | Prompt too large → 400 or silent truncation |
| **Fix** | Dynamic inject budget: `min(RAG_INJECT_MAX_CHARS, context_budget)`; lowered cap to ~22k chars; strip `data:` image embeds |
| **Commits** | `53566f9`, `8ab88df`, `56a0341` |

---

### 4.3 Empty help_md / wrong default scope

| | |
|---|---|
| **Symptom** | help_md category indexed zero docs; chat scoped wrong category |
| **Fix** | Fallback to `data/documents/` when MD/TXT empty; create help_md stub; default scope procedures; nested md glob |
| **Commits** | `932a157`, `e4f739c`, `7fb30b5`, `186050e` |

---

### 4.4 RAG repair tangent / false "not in docs"

| | |
|---|---|
| **Symptom** | Repair turn goes off-topic; false absent detection |
| **Fix** | Tighter absent detection; generic follow-up; skip NOT_FOUND collapse when context present |
| **Commits** | `5817d01`, `0fcee28` |

---

### 4.5 Image embed bloat in corpus

| | |
|---|---|
| **Symptom** | Base64 `data:` URIs in converted MD inflate prompts |
| **Fix** | `core/sop_text_clean.py` strips data URIs; keeps relative screenshot paths for `/api/rag-media` |
| **Commit** | `8ab88df` |

---

### 4.6 Admin category budget caps removed

| | |
|---|---|
| **Symptom** | Document manager blocked uploads when category “budget” exceeded |
| **Fix** | Removed per-category char/file caps; rely on RAG inject limits instead |
| **Commit** | `ad1bb26` |

---

### 4.7 Legacy interaction rows missing RAG context in admin

| | |
|---|---|
| **Symptom** | Old SQLite rows had no stored inject text in admin detail view |
| **Fix** | Lazy reconstruction (`?reconstruct_rag=1`) + backfill display for legacy rows |
| **Commits** | `06c104d`, `e87b82d` |

---

## 5. API & backend crashes

### 5.1 Admin overview 500 (Internal server error)

| | |
|---|---|
| **Symptom** | `/api/admin/documents/overview` returns generic 500 |
| **Root causes** | Invalid `RAG_DEFAULT_CATEGORY`; one bad category crashing whole overview; one corrupt file crashing full DocStore reload |
| **Fix** | Skip bad categories in overview; per-file skip on reload with logging |
| **Debug** | `API_EXPOSE_ERROR_DETAIL=true` temporarily; check `logs/api.log` |
| **Commits** | `a74cfe8`, documented in `ADMIN_INTERNAL_SERVER_ERROR.md` |

---

### 5.2 Circular import on API startup

| | |
|---|---|
| **Symptom** | uvicorn fails immediately on import |
| **Fix** | Break circular dependency between modules |
| **Commits** | `152a8af`, related startup fixes |

---

### 5.3 Missing settings import crash

| | |
|---|---|
| **Symptom** | API startup crash after settings page added |
| **Fix** | Restore missing import in `main.py` |
| **Commit** | `5cf0d9c` |

---

### 5.4 apply_plan syntax error

| | |
|---|---|
| **Symptom** | API won't start after admin documents change |
| **Fix** | Syntax fix in apply_plan |
| **Commit** | `0e8d359` |

---

### 5.5 Debug route registered before app creation

| | |
|---|---|
| **Symptom** | API startup crash |
| **Fix** | Register debug-log route after FastAPI app factory |
| **Commit** | `c2af777` |

---

### 5.6 Documents overview username kwarg

| | |
|---|---|
| **Symptom** | TypeError on overview endpoint |
| **Fix** | Correct keyword-only argument passing |
| **Commit** | `b2463c0` |

---

## 6. Admin console issues

### 6.1 Admin theme broken after redesign

| | |
|---|---|
| **Symptom** | Admin still showed dark-era hardcoded colors; toggle broken |
| **Fix** | Migrate `admin.css` to `var(--*)` tokens; fix CSS load order (theme before admin.css); file-swap stylesheets; decouple from OS `prefers-color-scheme` |
| **Commits** | `8aaa11f` → `5bc3dec` chain; `d228580`, `54b21a1` |

---

### 6.2 Admin performance (slow interaction list)

| | |
|---|---|
| **Symptom** | Loading all interactions with full response/metadata was slow |
| **Fix** | `summary=1` lightweight rows; pagination; infinite scroll; lazy RAG reconstruction |
| **Commit** | `525b73e`, ROADMAP §3.2 |

---

### 6.3 Git refresh vs RAG reload confusion

| | |
|---|---|
| **Symptom** | Admin git-refresh didn't reload corpus; or users expected RAG update from git alone |
| **Fix** | Separate endpoints: git-refresh (pull + build) vs rag-reload (re-index); clearer UI copy |
| **Commit** | `9ea94f6` |

---

### 6.4 Document manager UX glitches

| Issue | Fix |
|-------|-----|
| Drag-drop unreliable | Staged folder import with explicit rules |
| Duplicate filenames | Modal for overwrite one-by-one or all |
| Cancel pending upload deleted server file | Cancel without server delete |
| Documents tab not switching after deploy | Ready guard + deploy fix |
| Delete path resolution wrong | Fix delete path resolution |
| **Commits** | `d80eff5` → `fe2fdda` chain |

---

### 6.5 Admin login / auth alignment

| | |
|---|---|
| **Symptom** | Chat login used password-only; admin expected username |
| **Fix** | Unified username + password on chat; role-scoped admin API; French error messages |
| **Commits** | `3a1acf5`, `e323e31`, `986b366`, `c9f22d2` |

---

## 7. Frontend & chat UI issues

### 7.1 Blank SPA after deploy

| | |
|---|---|
| **Symptom** | Chat page blank; 404 on assets |
| **Fix** | `npm run build` in `web_test`; fail-closed check for `dist/index.html`; git-refresh runs build |
| **Commits** | `26ff835`, deploy docs |

---

### 7.2 Stale chat in localStorage

| | |
|---|---|
| **Symptom** | Refresh replays old transcript |
| **Mitigation** | Use "New chat" button; documented in DEPLOYMENT §12 |

---

### 7.3 Source preview 404

| | |
|---|---|
| **Symptom** | Clicking Source: fails — model cites title not filename |
| **Fix** | Fuzzy resolution: token overlap, heading match, filesystem scan |
| **Commits** | `5d2be75`, `cedc983` |

---

### 7.4 RAG debug line visible in chat

| | |
|---|---|
| **Symptom** | Internal debug metadata shown to users |
| **Fix** | Hide RAG debug line in chat UI |
| **Commit** | `43205c2` |

---

### 7.5 Chat settings UI removed

| | |
|---|---|
| **Change** | Removed client-side RAG settings UI; scope via API/category selector instead |
| **Commit** | `9a1e389` |

---

### 7.6 Brave browser forced colors

| | |
|---|---|
| **Symptom** | Theme looks wrong in Brave |
| **Mitigation** | File-swap + `color-scheme: only light|dark`; user must disable "Use Brave colors for all websites" |
| **Commits** | `4113d44`, `cda102c` |

---

## 8. Logigramme subsystem issues

### 8.1 Initial rollback

| | |
|---|---|
| **Symptom** | Early logigramme in web caused instability |
| **Fix** | Rolled back from web (`54b21a1`); re-shipped with isolated architecture (`8c3b917` onward) |
| **Debug session** | `95261d8` scroll instrumentation — ephemeral; fixed in `a15bc2f`, `19c9f1e` |

---

### 8.2 Draft vs publish confusion

| | |
|---|---|
| **Symptom** | Edits visible to all before ready |
| **Fix** | Per-user auto-save drafts; explicit **Publier** to shared `.mmd`; badge states |
| **Commits** | `c90227e`, `1ea0c89`, `b3a95e9` |

---

### 8.3 Preview zoom/scroll/pan

| | |
|---|---|
| **Symptom** | Large diagrams clipped; zoom unusable |
| **Fix** | Double-click focus zoom; scroll when zoomed; 400% max zoom; toolbar pan |
| **Commits** | `eb3fe36`, `a15bc2f`, `7ad7066`, `19c9f1e` |

---

### 8.4 RAG Mermaid tool conflation

| | |
|---|---|
| **Symptom** | Mermaid incorrectly merged into chat text path |
| **Fix** | Split Mermaid from chat text; metadata-only rendering |
| **Commit** | `19c9f1e` |

---

### 8.5 Format evaluation (May 2026)

| Format | Syntax pass rate |
|--------|------------------|
| mermaid, dot, plantuml, html, json_graph | 100% |
| svg | 33% |

**Decision:** Mermaid chosen as production format. Report: `outputs/logigramme_eval/report_20260521T163814Z.json`

---

## 9. Major feature deliveries (changelog summary)

### Phase 1 — Foundation (Apr 2026)
- Initial harness: vLLM + FastAPI + SQLite (`0377808`)
- BM25 doc retrieval + RAG inject (`931535a`)
- Gemma 4 26B support, TP=2 (`5a33dcf`)
- Category-aware RAG + frontend dropdown (`52e687b`)
- Port 8002 fix (`a0187b7`)

### Phase 2 — RAG maturity (Apr–May 2026)
- Full-category inject for small corpora (`7619b25`, `e91f2c1`)
- DOCX → Markdown pipeline; prefer `documents_md` (`e91f2c1`, `c4fc8fd`)
- Liked-only answer cache (`7619b25`)
- FR/Darija BM25 hints; stricter language policy (`d364ba3`, `4221a12`)
- RAG repair turn; absent-docs detection (`dd8e5fc`, `0fcee28`)
- Continuation on length cutoff (`1c10db7`)
- Greedy full-doc inject (`9b76f22`)
- RAG scope selector: procedures / help / all (`2369d1a`)

### Phase 3 — Agentic RAG (May 2026)
- Optional agentic path with map + tools (`fe0dcab`)
- Gemma 4 vLLM tool flags (`52d74a7`)
- E5 embeddings + BM25 fallback (`d72f598`)
- Catalog-driven retrieval without embeddings (`9a44d3f`)
- Two-phase router + answer (`264ed34`, `ae0e293`, `ed51611`)
- Multi-scope auto-agentic (`b3a95e9`)

### Phase 4 — Admin platform (May 2026)
- Document manager with staging (`d80eff5` → `5704c5f`)
- Role-based auth: user / manager / administrator (`3a1acf5`)
- User management tab + CLI (`2369d1a`, `986b366`)
- Resilient overview + per-file skip (`a74cfe8`)
- Git refresh vs RAG reload split (`9ea94f6`)
- Administrator settings page (`a8f0420`)

### Phase 5 — UX & preview (May 2026)
- Document preview modal — isolated from chat (`5d2be75`)
- Shared light/dark theme chat + admin (`8aaa11f` → `5bc3dec`)
- Admin performance: summary pagination (`525b73e`)
- Source title → docx/md resolution (`cedc983`)

### Phase 6 — Logigrammes (May 2026)
- Procedure Mermaid generation (`8c3b917`)
- Draft/publish workflow (`c90227e`, `1ea0c89`)
- Chat explicit logigramme intent + PNG export (`95261d8`, `37c2afa`)
- Preview tab in document modal (`8c3b917`)
- Modal UX overhaul (`b2463c0`, `cb83026`)

### Phase 7 — Polish (May 2026)
- Greeting/off-topic preflight (`1b81df5`)
- Composite classic RAG tests (`0f402fb`, `1b81df5`)
- Logigramme zoom to 400% (`7ad7066`)

### Phase 8 — Thread + Darija pipeline (Jun 2026)
| | |
|---|---|
| **Symptom** | Darija annulation dispute misread; English follow-up (“where is history”) blocked as off-topic; answers drift to French |
| **Root cause** | Preflight catch-all without `history`; BM25 on isolated turn; sparse Darija→FR hints; per-turn language only |
| **Fix** | Thread-aware preflight + `retrieval_anchor_query`; broader `_SENDIT_DOMAIN`; `resolve_answer_language` + `LANGUAGE_BLOCK` |
| **Tests** | `scripts/test_conversation_intent.py`, `test_retrieval_anchor.py`, `eval_thread_regression.py`, `test_answer_language.py` |

### Phase 9 — Case brief + reasoning compliance (Jun 2026)
| | |
|---|---|
| **Symptom** | Wrong scenario (invented refusal / failed delivery); BM25 skew to annulation-fee docs; mixed SOP branches in one answer |
| **Root cause** | Single-shot answer without structured case model; lexical BM25 on `annul` without staff intent |
| **Fix** | Toggleable `CASE_BRIEF_ENABLED` (`core/case_brief.py`); `CAS UTILISATEUR` + `REASONING_REPAIR_ENABLED` (`core/reasoning_compliance.py`); tighter `SYSTEM_PROMPT` application rules |
| **Flags** | `CASE_BRIEF_ENABLED`, `CASE_BRIEF_TEMPERATURE`, `CASE_BRIEF_MAX_TOKENS`, `REASONING_REPAIR_ENABLED` in `.env` |
| **Tests** | `test_case_brief.py`, `eval_reasoning.py`, `fixtures/reasoning_cases.json`; `rag_audit.py --brief-json` |

---

## 10. Known remaining issues & mitigations

| Issue | Status | Mitigation |
|-------|--------|------------|
| Corpus lost on pod restart | Open | Re-upload docs or use persistent volume |
| Sensitive docs in git history | Open | `git filter-repo` if required |
| Brave forced colors | Partial | User browser setting |
| Admin infinite scroll edge cases | Minor | Optional "Charger plus" button (ROADMAP) |
| Logigramme fidelity on complex SOPs | In review | Manual review + refine prompts |
| Security hardening | Deferred | Focus on answer quality first (ROADMAP) |
| CI/CD automation | Planned | GitHub Actions smoke tests |
| Untracked local scripts | Open | `pod_rag_stats.py`, `rag_mode_stats.py` — commit or document |
| Eval toggle stub (admin) | Open | UI stub only (`3227a5f`); no full eval pipeline |
| Darija annulation thread quality | Mitigated (Jun 2026) | Enable `CASE_BRIEF_ENABLED=true` on pod; `eval_reasoning.py`; `rag_audit.py --brief-json` |

---

## 11. Artifacts folder (undocumented diagnostics)

The `artifacts/` directory holds **~19 one-off Python scripts** from pod debugging sessions (e.g. `pod_fix_vllm.py`, `pod_install_sglang.py`, `check_gpu.py`). They are **not** part of the production deploy path. Indexed in [`COVERAGE_INDEX.md`](COVERAGE_INDEX.md) §3.

---

## 12. Debugging playbook

### Generic 500 on admin
1. `tail -80 logs/api.log`
2. `curl -sS http://127.0.0.1:8000/health`
3. Set `API_EXPOSE_ERROR_DETAIL=true`; restart API; **disable after**

### Answer not in corpus
```bash
python scripts/rag_audit.py "query snippet" procedures
```
If theme counters = 0 → topic absent. If > 0 → check inject size and admin RAG preview.

### Agentic not working
1. Confirm `AGENTIC_RAG_ENABLED=true`
2. Check vLLM tool flags in `start_vllm.sh`
3. Run `python scripts/test_agentic_rag_pod.py` on pod

### Deploy verification
```bash
git log -1 --oneline
curl -sS http://127.0.0.1:8000/health
curl -sS http://127.0.0.1:8002/v1/models
```

---

## 13. Related documentation

| Document | Topic |
|----------|-------|
| `project_logs/deployment_issues_2026-04-28.md` | First RunPod deploy postmortem |
| `project/ADMIN_INTERNAL_SERVER_ERROR.md` | Admin 500 debugging |
| `project/DEPLOYMENT.md` | Pitfalls checklist §9 |
| `project/ROADMAP.md` | Open product items |
| `project/CHANGELOG.md` | All 147 commits |
| `project/COVERAGE_INDEX.md` | Documentation map & gaps |
| `project/SUMMARY_ARCHITECTURE.md` | System design reference |
| `project/SUMMARY_README.md` | How to use each component |
