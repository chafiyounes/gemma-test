# Documentation coverage index — gemma-test

**Purpose:** Map every major project area to where it is documented, flag gaps, and state what **no document type can replace**.

**Companion summaries:** [`SUMMARY_ARCHITECTURE.md`](SUMMARY_ARCHITECTURE.md) · [`SUMMARY_BUGS_AND_CHANGES.md`](SUMMARY_BUGS_AND_CHANGES.md) · [`SUMMARY_README.md`](SUMMARY_README.md)  
**Full commit list:** [`CHANGELOG.md`](CHANGELOG.md) (147 commits)

---

## 1. Document map (where to look)

| Topic | Primary doc | Also covered in |
|-------|-------------|-----------------|
| System design & data flow | `SUMMARY_ARCHITECTURE.md`, `ARCHITECTURE.md` | `CHANGELOG.md` (commits) |
| Deploy & SSH / RunPod | `SUMMARY_README.md` §6, `DEPLOYMENT.md` | `docs/runbook_runpod_quick_start.md`, `project_logs/deployment_issues_2026-04-28.md` |
| Corpus folders & pod sync | `DATA_LAYOUT.md` | `SUMMARY_ARCHITECTURE.md` §10 |
| Problems & fixes (narrative) | `SUMMARY_BUGS_AND_CHANGES.md` | `ADMIN_INTERNAL_SERVER_ERROR.md`, `DEPLOYMENT.md` §9 |
| How to use each component | `SUMMARY_README.md` | `web_test/README.md` |
| Every commit (audit trail) | **`CHANGELOG.md`** | git log |
| Product priorities | `ROADMAP.md` | `SUMMARY_ARCHITECTURE.md` §15 |
| Document preview subsystem | `DOCUMENT_PREVIEW.md` | Summaries §preview |
| Logigrammes | `LOGIGRAMME.md` | Summaries §logigramme |
| UI theme | `DESIGN_SYSTEM.md` | Summaries §frontend |
| First deploy postmortem | `project_logs/deployment_issues_2026-04-28.md` | `SUMMARY_BUGS_AND_CHANGES.md` §2 |

---

## 2. Feature → documentation matrix

| Feature / subsystem | Code location | Documented? | Best reference |
|---------------------|---------------|-------------|----------------|
| Classic RAG (BM25 + full inject) | `core/documents.py`, `core/llm.py` | ✅ Yes | `ARCHITECTURE.md`, summaries |
| Agentic two-phase RAG | `core/agentic_rag.py` | ✅ Yes | `ARCHITECTURE.md` §2, summaries |
| Chat policy (lang, profanity, preflight) | `core/chat_policy.py` | ✅ Yes (updated) | `SUMMARY_ARCHITECTURE.md` §7 |
| Continuation message anchoring | `core/chat_policy.py` | ✅ Yes (updated) | Summaries |
| Liked-answer cache | `core/persistence.py`, `api/main.py` | ✅ Yes (updated) | Summaries |
| Rate limiting | `api/main.py`, `settings.py` | ✅ Yes (updated) | Summaries |
| Feedback (like/dislike + reasons) | `web_test/…/MessageBubble.jsx`, SQLite | ✅ Yes (updated) | `SUMMARY_README.md` §3.9 |
| DOCX → MD pipeline | `core/docx_to_md.py` | ✅ Yes (updated) | Summaries |
| SOP section strip / condense | `core/sop_text_clean.py`, settings | ✅ Yes (updated) | Summaries |
| Help-center scraper | `scrape_sendit.py` → `sendit_docs/` | ✅ Yes (updated) | `SUMMARY_README.md` §3.10 |
| Document preview modal | `core/document_preview.py` | ✅ Yes | `DOCUMENT_PREVIEW.md` |
| Logigrammes | `core/logigramme_*.py` | ✅ Yes | `LOGIGRAMME.md` |
| Admin document manager | `core/documents_admin.py` | ✅ Yes | Summaries, `CHANGELOG.md` |
| Auth & roles | `core/security.py`, `core/persistence.py` | ✅ Yes | Summaries |
| Administrator settings page | `core/admin_settings_snapshot.py` | ✅ Yes (updated) | `CHANGELOG.md` May 25 |
| Shared light/dark theme | `shared/theme/` | ✅ Yes | `DESIGN_SYSTEM.md` |
| vLLM inference | `scripts/start_vllm.sh` | ✅ Yes | `DEPLOYMENT.md` §7 |
| Transformers fallback | `scripts/serve_gemma4.py` | ✅ Yes | Summaries |
| Manim architecture videos | `scripts/manim_gemma_architecture.py` | ✅ Yes (updated) | `CHANGELOG.md` |
| SGLang experiment (abandoned) | `artifacts/pod_install_sglang.py` | ✅ Yes (updated) | `SUMMARY_BUGS_AND_CHANGES.md` |
| RunPod recycle / VRAM reclaim | `scripts/runpod_recycle_pod.py` | ✅ Yes (updated) | Summaries |
| Eval toggle stub (admin) | admin UI | ⚠️ Stub only | `CHANGELOG.md` `3227a5f` |
| CI/CD | — | ❌ Planned | `ROADMAP.md` §6 |
| GitHub Issues / PRs | — | ❌ None used | 147 direct commits |

---

## 3. Scripts inventory → documentation

| Script category | Examples | In SUMMARY_README? |
|-----------------|----------|-------------------|
| Deploy / pod | `deploy_runner.py`, `pod_cmd.py`, `fetch_pod_tar.py` | ✅ |
| Inference | `start_vllm.sh`, `serve_gemma4.py`, `bench_vllm.py` | ✅ partial |
| RAG audit / test | `rag_audit.py`, `test_rag_inject_greedy.py`, `corpus_disk_vs_store.py` | ✅ |
| Agentic test | `test_agentic_rag_pod.py`, `bootstrap_agentic_map.py` | ✅ partial |
| Corpus export | `export_sop_to_md.py`, `export_sop_to_txt.py`, `upload_docs.py` | ✅ (updated) |
| Logigramme eval | `eval_logigramme_formats.py`, `prototype_logigramme.py` | ✅ (updated) |
| User ops | `manage_users.sh` | ✅ |
| Diagnostics (repo root) | `artifacts/pod_*.py` (19 files) | ✅ indexed here |
| **Untracked local** | `pod_rag_stats.py`, `rag_mode_stats.py` | ⚠️ Not in git |

---

## 4. Known documentation gaps (honest list)

These were **missing or thin** before this audit; status after May 2026 doc pass:

| Gap | Status | Action taken |
|-----|--------|--------------|
| No commit-by-commit log | **Fixed** | Added `CHANGELOG.md` |
| No “what’s documented where” | **Fixed** | This file |
| Liked-answer cache | **Fixed** | Added to all 3 summaries |
| Rate limiting details | **Fixed** | Added to summaries |
| Feedback UX flow | **Fixed** | Added to README summary |
| Conversation preflight | **Fixed** | Added to architecture + bugs |
| `scrape_sendit.py` pipeline | **Fixed** | Added to README summary |
| DOCX conversion details | **Fixed** | Added to architecture summary |
| Manim presentation scripts | **Fixed** | Added to CHANGELOG + architecture |
| SGLang dead-end experiment | **Fixed** | Added to bugs summary |
| `artifacts/` diagnostic scripts | **Fixed** | Indexed here + bugs appendix |
| Only one dated incident log | **Open** | Consider `project_logs/YYYY-MM-DD.md` per major incident |
| Sensitive docs in git history | **Open** | Documented; needs `git filter-repo` if required |
| Live pod state / corpus version | **Not doc-able statically** | Operational checklist only |
| Answer quality eval scores | **Open** | No standing eval report except logigramme format eval |
| Informal Cursor session decisions | **Lost unless written** | Use CHANGELOG + project_logs for future |

---

## 5. What three summary types cannot cover

Even with perfect maintenance, split docs have inherent limits:

| Need | Why summaries + CHANGELOG are not enough |
|------|------------------------------------------|
| **Live pod state** | Model loaded today, disk free, current errors — must query pod |
| **Corpus content audit** | Which SOPs are outdated — content lives outside git |
| **Quality metrics** | Darija/EN accuracy on real questions — needs eval dataset + scores |
| **Prompt A/B rationale** | Why each SYSTEM_PROMPT phrase exists — needs design notes or blame + context |
| **Security audit** | Access reviews, secret rotation — separate process |
| **Cost / RunPod economics** | GPU hours, $/query — billing data |
| **Automated test matrix** | Which of 20+ scripts run in CI vs manually — needs CI config |
| **Tacit team knowledge** | “We tried X and rejected it” — needs incident/decision logs |

**Recommended additions for “complete” project memory:**

1. **`CHANGELOG.md`** — ✅ added (commit audit trail)
2. **`COVERAGE_INDEX.md`** — ✅ this file
3. **`project_logs/YYYY-MM-DD-<topic>.md`** — optional per incident (only one exists today)
4. **`eval/` or `outputs/` reports** — periodic RAG quality runs (logigramme eval is the precedent)
5. **CI workflow** — when added, document in `ROADMAP.md` + README

---

## 6. Change-tracking maturity (assessment)

| Source | Coverage | Reliability |
|--------|----------|-------------|
| Git commits | 147 commits, all listed in CHANGELOG | High for code; variable message quality |
| `project/*.md` | ~15 files, updated ad hoc | Medium; strong on architecture/deploy |
| `project_logs/` | 1 file (2026-04-28) | Low frequency |
| GitHub Issues | 0 | Not used |
| Agent / Cursor sessions | Not archived in repo | Not reliable |
| Summaries (3 files) | Narrative synthesis | Good for presentations; not exhaustive alone |

**Conclusion:** The project **did not** keep a running log of every problem until now. **`CHANGELOG.md` + updated summaries + this index** close most of the gap for code and known incidents. Future incidents should add a dated `project_logs/` entry.

---

## 7. Quick navigation for reports

| Audience | Read first | Then |
|----------|------------|------|
| Executive / sponsor | `SUMMARY_ARCHITECTURE.md` §1 | `ROADMAP.md` §1 |
| Technical architect | `SUMMARY_ARCHITECTURE.md` | `ARCHITECTURE.md`, `CHANGELOG.md` |
| Ops / on-call | `SUMMARY_README.md` §6–8 | `DEPLOYMENT.md`, runbook |
| Postmortem / audit | `SUMMARY_BUGS_AND_CHANGES.md` | `CHANGELOG.md`, `project_logs/` |
| New developer | `SUMMARY_README.md` | `COVERAGE_INDEX.md`, `.env.example` |
| “Did we document X?” | **This file** §2 | `grep` / `CHANGELOG.md` |

---

## 8. Related files (full list)

```
project/
├── SUMMARY_ARCHITECTURE.md      ← system design (presentation)
├── SUMMARY_BUGS_AND_CHANGES.md  ← problems & fixes (presentation)
├── SUMMARY_README.md            ← how to use (presentation)
├── CHANGELOG.md                 ← all commits (audit)
├── COVERAGE_INDEX.md            ← this file
├── ARCHITECTURE.md              ← detailed technical reference
├── DEPLOYMENT.md
├── DATA_LAYOUT.md
├── DOCUMENT_PREVIEW.md
├── LOGIGRAMME.md
├── DESIGN_SYSTEM.md
├── ROADMAP.md
└── ADMIN_INTERNAL_SERVER_ERROR.md

project_logs/
└── deployment_issues_2026-04-28.md

docs/
└── runbook_runpod_quick_start.md
```
