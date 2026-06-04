# Changelog — gemma-test (SendBot)

**Repository:** [github.com/chafiyounes/gemma-test](https://github.com/chafiyounes/gemma-test)  
**Scope:** All **147** commits on `main` (2026-04-28 → 2026-05-25)  
**Format:** Grouped by date and theme. Each line is one commit (`hash` — subject).

For narrative context (root causes, fixes), see [`SUMMARY_BUGS_AND_CHANGES.md`](SUMMARY_BUGS_AND_CHANGES.md).  
For “what is documented where”, see [`COVERAGE_INDEX.md`](COVERAGE_INDEX.md).

---

## April 2026

### 2026-04-28 — Project init & first deploy

| Hash | Change |
|------|--------|
| `0377808` | init: gemma test harness - vLLM + FastAPI + SQLite |
| `5a33dcf` | feat: add Gemma 4 26B-A4B support, tensor-parallel-size 2 for dual A40 |
| `931535a` | feat: BM25 doc retrieval + RAG-style SOP context injection; safer vLLM params |
| `a0187b7` | fix: vLLM on port 8002 (avoid stale 8001 sidecar) |
| `7d78377` | data: add 60 SOP documents for RAG context |
| `4bea39c` | security: remove sensitive SOP documents from public repo (data/documents/ is gitignored) |

### 2026-04-29 — Category RAG & inference pivot

| Hash | Change |
|------|--------|
| `52e687b` | feat: category-aware RAG with per-folder doc selection + frontend dropdown + Gemma 4 deploy script |
| `61713f4` | fix: vLLM max-num-batched-tokens for Gemma 4 multimodal + use Gemma 4 in deploy |
| `c5c30b9` | feat: replace vllm with transformers inference server (cu128 compat) |

### 2026-04-30 — GPU / Transformers stability

| Hash | Change |
|------|--------|
| `9c1b5f7` | fix: use return_dict=True in apply_chat_template to avoid BatchEncoding AttributeError |
| `db73c56` | fix: auto-detect first available CUDA device, force device_map to single GPU to eliminate CPU/meta offload |
| `7c2bbde` | fix: use device_map=auto with max_memory for both A40s, kill stale OOM processes before GPU load, add expandable_segments |
| `7f23e2c` | fix: CUDA_VISIBLE_DEVICES=1 to hide inaccessible GPU0, add bitsandbytes INT8 quantization (52GB->26GB, fits single A40) |
| `ad64af4` | fix: use BitsAndBytesConfig(load_in_8bit=True) for transformers 5.6.x compatibility |

---

## May 2026

### 2026-05-04 — Dual-GPU, Gemma 3 stability pass, return to vLLM

| Hash | Change |
|------|--------|
| `9eaffda` | fix: dual-GPU deployment, inject all 10 SOPs, fix frontend API bugs |
| `67a683f` | fix: add missing AI dependencies to requirements.txt |
| `1859f7c` | Update prompt engineering and upload scripts |
| `4a935d4` | Fix vLLM nan error and update prompt |
| `65237dd` | Final stability and accuracy fixes: float16, greedy decoding, and exhaustive prompt |
| `a2d07ca` | Debugging CUDA assert: bfloat16, 20k context limit, and CUDA blocking |
| `59c000f` | Enable Flash Attention 2 and stabilize context for production |
| `d841be5` | Stability First: SDPA, 15k context limit, bfloat16 |
| `26ba350` | Switch to stable Gemma 3 27B model and keep 15k context for production stability |
| `753fa36` | Hard-force Gemma 3 for stability |
| `19d4b51` | Fix tokenizer: use_fast=False for Gemma 3 stability |
| `1274a9d` | Switch Gemma 4 26B serving to vLLM 0.19 (TP=2 on 2x A40, ~80 tok/s) |

### 2026-05-05 — RAG quality, context budget, ops

| Hash | Change |
|------|--------|
| `e0f63c3` | RAG + UX: continuation queries, EN/FR hints, longer outputs, policy messages |
| `d364ba3` | RAG: FR/Darija-only BM25 hints; system prompt; architecture docs |
| `f8e5de8` | fix: avoid truncated answers (raise max_tokens + timeouts, prompt completeness) |
| `2b6d2d5` | fix: vLLM context window vs full RAG (default max-model-len 16384) |
| `3cdadf6` | fix: align RAG inject with vLLM context (14k chars, default max-len 12288) |
| `b819aea` | ops: longer vLLM wait before API; clearer inference unreachable message |
| `62da199` | docs: actions roadmap; secure deploy_pod env vars; frontend 0.1.0 |

### 2026-05-06 — Language policy, admin dashboard, RAG repair

| Hash | Change |
|------|--------|
| `4221a12` | fix(lang): stricter non-FR Latin gate, French-only notice; expand BM25 FR hints for logistics |
| `d289fb5` | chore(vllm): preflight when GPU free VRAM too low; clarify ConnectError message for stuck VRAM |
| `d45256c` | fix(vllm): reclaim VRAM before mem check; optional gpu reset; RunPod REST recycle script |
| `a637e29` | fix(api): bootstrap requirements-api.txt when uvicorn missing (fresh RunPod) |
| `3227a5f` | feat(rag): prompt for adjacent SOP synthesis; slim admin UI; eval toggle stub; drop client RAG debug |
| `96281a4` | vLLM: retry transient connection errors; friendlier unavailable messages |
| `0751f7f` | RAG: rank docs by query for inject; EN/darija BM25 recall; larger inject cap |
| `4c102c6` | Fix admin dashboard (feedback shape, RAG panel, sessions); default RAG category; persist rag meta |
| `c7e567b` | Admin UI: hide toolbar until admin login; pre-auth instructions |
| `0fcee28` | rag_audit script; stricter absent-docs prompt; expand NOT_FOUND markers; BM25 hint déjà |
| `dd8e5fc` | RAG: repair turn when model claims absent despite inject; skip NOT_FOUND collapse if ctx; regression test script |
| `7619b25` | RAG: condense + full-category inject; liked-only answer cache |

### 2026-05-07 — DOCX pipeline, admin RAG visibility, inject tuning

| Hash | Change |
|------|--------|
| `e91f2c1` | feat: DOCX to Markdown pipeline; RAG prefers documents_md |
| `c4fc8fd` | feat: full-docx MD conversion, DocStore.reload, admin git-refresh |
| `35c6df6` | feat: strip SOP sections after 5; deploy defaults to api-only restart |
| `2383487` | docs: Manim scenes for filesystem + system architecture (with bottom captions) |
| `878e8c6` | fix: restore condense_sop_plaintext for RAG context building |
| `43b57df` | fix: disable section truncation by default for RAG context |
| `06c104d` | feat(admin): show full injected RAG context in interaction detail |
| `e87b82d` | fix(admin): reconstruct and show RAG context for legacy interaction rows |
| `f3690ae` | tune: raise inject budget to reduce context truncation |
| `56a0341` | fix: auto-retry on vLLM context-length 400 by reducing max_tokens |
| `a52fd10` | tune: maximize context budget without extra VRAM allocation |

### 2026-05-08 — Chat UI & document manager

| Hash | Change |
|------|--------|
| `dffd9d3` | fix: improve assistant message formatting in chat UI |
| `d80eff5` | feat(admin): add document manager with budget guardrails |
| `5704c5f` | fix(admin): make documents tab reliably switch after deploy |
| `12f86e6` | feat(admin): add staged folder-style document manager |
| `b1a3a30` | feat(admin): support staged folder import rules and compact rows |
| `c95940b` | fix(admin): support recursive folder drop extraction reliably |
| `3ecb11a` | admin docs: remove drag-drop, multi-select add files |

### 2026-05-09 – 2026-05-12 — Agentic RAG

| Hash | Change |
|------|--------|
| `fe0dcab` | feat: optional agentic RAG test path (map + tools, gated) |
| `52d74a7` | fix: Gemma 4 vLLM tool flags for agentic RAG; pod test suite |
| `88e1089` | test: clearer vLLM 400 and agentic metadata diagnostics; remote hint for vLLM restart |
| `d72f598` | feat(agentic): LLM map extraction, multilingual-e5 index + cosine search with BM25 fallback |
| `e575ddb` | fix(agentic): index cache, dim guard, vLLM transient retries, safe JSON parse |
| `0a8760f` | chore: pod post-deploy verify script (deps, index, chat smoke) |
| `2f948bf` | fix: UTF-8 stdout for pod verify on Windows; wait for vLLM before tests |
| `9a44d3f` | refactor: catalog-driven agentic retrieval without embeddings |
| `7d8eb5b` | fix: align post-deploy Darija smoke with procedures corpus (coordinates during delivery) |
| `6518099` | feat(admin): single-corpus bulk uploads, optional category, flat folder import |
| `30bc3b4` | fix(admin docs): ready guard for uploads, delete whole category, workflow copy, emoji save/cancel |
| `26ff835` | chore: fail-closed web deploy bundle check, clearer restart_api tmux hint, 413 upload hint |
| `ad1bb26` | Document admin: remove category budget caps, fix delete path resolution, API doc routes, restart_api cleanup |
| `264ed34` | Agentic RAG: router limits (target 5, max 10), retry prompt, fetch_count metadata, pod test accepts two-phase mode |
| `9b76f22` | documents: keep RAG helpers (_best_window_for_query, greedy inject) required by agentic_rag |
| `ae0e293` | Agentic router: force request_documents on first vLLM round (avoid empty tool_rounds) |
| `ed51611` | Two-phase agentic: preserve router tool_rounds in rag metadata (answer phase no longer clears it) |
| `03861c1` | push_to_runpod: document gateway SFTP limitation; prefer git pull |

### 2026-05-14 – 2026-05-15 — Auth, admin documents

| Hash | Change |
|------|--------|
| `3a1acf5` | feat(auth): administrator, manager, and user roles with scoped admin API |
| `e323e31` | fix(web): username + password on chat login (sync with /auth/login) |
| `4e90e1c` | fix(auth): optional SEED_STAFF_SYNC_PASSWORDS and French login error |
| `986b366` | feat(ops): scripts/manage_users.sh for add/role/password without redeploy |
| `c9f22d2` | fix: align admin login HTML, chat boot UX, and scripts with username auth |
| `8beba4d` | feat(admin-ui): document platform UX — dropzone, staging bar, clearer file rows |
| `77adb79` | fix(admin): compact doc rows, replace file, clearer apply-plan errors |
| `a74cfe8` | fix(rag,admin): resilient overview + DocStore load; document 500 debug |
| `f75be2c` | feat(admin): add .md uploads, simplify import UX, clarify refresh |
| `f872d49` | fix(admin): cancel pending upload/replace/move without server delete |
| `fe2fdda` | feat(admin): modal for duplicate filenames (overwrite one-by-one or all) |

### 2026-05-18 — Corpus layout, help_md, RAG inject hardening

| Hash | Change |
|------|--------|
| `3600033` | chore(cursor): rule to push and sync RunPod after code changes |
| `8229874` | Sync: RAG/chat unify, admin docs UX, web build/git-refresh, cache headers, user CLI |
| `1aab527` | chore: stop versioning local document corpora; ignore upload paths |
| `186050e` | fix: restore help_md RAG bootstrap, merge retrieval, and RunPod materialize step |
| `e4f739c` | fix: create data/documents/help_md stub so DocStore indexes help markdown |
| `2369d1a` | feat: RAG scope selector (procedures / help / all), admin users tab, user list and password APIs |
| `b8bc211` | feat(admin_site): Utilisateurs tab for accounts (administrator role) |
| `9a1e389` | Remove chat settings UI; improve vLLM 400 retries and error hints |
| `7fb30b5` | RAG: index nested help_md/procedures md; default chat scope procedures; MAX_NEW_TOKENS 2048 |
| `f21e63c` | Docstring: note recursive md/txt glob |
| `32db789` | Add corpus_disk_vs_store.py to audit on-disk RAG files vs index |
| `932a157` | DocStore: fall back to data/documents when MD/TXT index zero docs (fix empty help_md) |
| `a578151` | Document corpus layout, pod fetch script, chat UX and RAG hints |
| `78cb441` | Docs: note Windows filename normalization when syncing procedures from pod |
| `9ea94f6` | Fix admin Git vs RAG controls; restore chat category scope |
| `53566f9` | Fix RAG inject budget to stay under vLLM max context |
| `43205c2` | Hide RAG debug line in chat UI; Darija retrieval hints; answer language |
| `5817d01` | Fix RAG repair tangent: generic follow-up, tighter absent detection |
| `1c10db7` | Stop mid-answer cutoffs: fix RAG inject floor, add vLLM continuation |
| `13a6afd` | Stronger anti-truncation: more continuations, tighter RAG, arabizi hint |
| `8ab88df` | RAG: smaller inject cap; strip image embeds from corpus text |

### 2026-05-19 – 2026-05-21 — Document preview & theme

| Hash | Change |
|------|--------|
| `5d2be75` | feat(preview): Source-line document modal isolated from chat |
| `f41944e` | chore: pod smoke script for document preview API |
| `948eda2` | fix: URL-encode document name in preview smoke test |
| `cedc983` | fix(preview): resolve Source titles to docx/md paths on disk |
| `8aaa11f` | design: shared light/dark theme for chat and admin |
| `83a1417` | fix: decouple SendBot theme from OS color scheme |
| `4113d44` | fix: harden theme against Brave forced colors |
| `b520258` | fix: unify light theme and theme toggle across chat and admin |
| `cda102c` | fix: file-swap theme stylesheets to resist browser forced colors |
| `5bc3dec` | fix: restore admin styling — load theme CSS before admin.css |
| `525b73e` | Fix admin theme/perf, source links, and add logigramme generation |
| `54b21a1` | Soften light theme, fix admin dark mode, rollback logigramme from web |
| `4a2bd61` | docs: add logigramme format eval results from pod run |

### 2026-05-22 – 2026-05-23 — Logigrammes

| Hash | Change |
|------|--------|
| `8c3b917` | Fix admin theme toggle and add procedure logigrammes (Mermaid) |
| `152a8af` | fix: break circular import that crashed API on startup |
| `d228580` | Fix admin theme toggle and polish logigramme modal UX |
| `b3a95e9` | Fix logigramme prompts/validation and route all-documents RAG through agentic catalog |
| `dec6c1b` | Make logigramme Mermaid editable and prompt for richer procedure detail in labels |
| `c90227e` | Add logigramme draft vs publish workflow and exhaustive generation prompts |
| `1ea0c89` | Overhaul logigramme modal UX with per-user auto-save drafts |
| `b2463c0` | Fix documents overview username passed as keyword-only arg |
| `0e8d359` | Fix apply_plan syntax error that prevented API startup |
| `eb3fe36` | Add double-click focus zoom to logigramme preview |
| `37c2afa` | Add logigramme PNG export, explicit chat diagrams, and fix preview zoom/scroll |
| `95261d8` | Add logigramme scroll debug instrumentation for session a662c1 |
| `a15bc2f` | Fix logigramme scroll, zoom toolbar, and pan across admin and chat |
| `c2af777` | Fix API startup crash: register debug-log route after FastAPI app is created |
| `cb83026` | Restructure logigramme modal: tall preview left, controls sidebar right |
| `19c9f1e` | Fix logigramme drafts, document preview, and RAG Mermaid tool |
| `7ad7066` | Raise logigramme zoom to 400% and split Mermaid from chat text |

### 2026-05-25 — Settings page, preflight, tests

| Hash | Change |
|------|--------|
| `a8f0420` | Add administrator settings page with RAG mode and env snapshot |
| `5cf0d9c` | Fix API startup crash: restore missing settings import in main.py |
| `1b81df5` | Add greeting/off-topic preflight replies and composite classic RAG tests |
| `0f402fb` | Add remote runner for composite classic RAG tests on the pod |

---

## Appendix — commits by theme (cross-index)

| Theme | Commits (sample) |
|-------|------------------|
| **Inference / GPU** | `a0187b7`, `c5c30b9`, `7f23e2c`, `1274a9d`, `d45256c`, `52d74a7` |
| **RAG retrieval & inject** | `931535a`, `7619b25`, `53566f9`, `8ab88df`, `9b76f22` |
| **Agentic RAG** | `fe0dcab` → `ed51611`, `9a44d3f`, `b3a95e9` |
| **DOCX / corpus** | `e91f2c1`, `c4fc8fd`, `932a157`, `186050e` |
| **Admin platform** | `d80eff5` → `a74cfe8`, `a8f0420` |
| **Auth & users** | `3a1acf5`, `986b366`, `2369d1a` |
| **Theme / UX** | `8aaa11f` → `5bc3dec`, `dffd9d3` |
| **Document preview** | `5d2be75`, `cedc983` |
| **Logigrammes** | `8c3b917` → `7ad7066` |
| **Security incident** | `7d78377`, `4bea39c` |
| **Docs only** | `a578151`, `2383487`, `4a2bd61` |

---

## Not in git (local / ephemeral)

These exist in the workspace but are **not committed** as of last audit:

| Path | Notes |
|------|-------|
| `scripts/pod_rag_stats.py` | Remote RAG stats runner |
| `scripts/rag_mode_stats.py` | RAG mode statistics |
| `scripts/_pod_rag_stats_remote.py` | Helper for pod stats |
| `artifacts/*.py` | One-off pod diagnostics (SGLang install, vLLM fix, etc.) — not tracked |

Regenerate this file after major releases:

```bash
git log --format="%h|%ad|%s" --date=short --reverse
```
