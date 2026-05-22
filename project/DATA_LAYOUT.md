# Document data layout — gemma-test

**See also:** [`ARCHITECTURE.md`](ARCHITECTURE.md) (retrieval order), [`DEPLOYMENT.md`](DEPLOYMENT.md) (RunPod, syncing).

---

## 1. Canonical source: `data/documents/<category>/`

- **Every RAG category is a subfolder** of `data/documents/`. Files dropped **directly** under `data/documents/` (no subfolder) are **ignored** by `DocStore`.
- This tree is the **authoritative place** for originals: `.docx`, optional `pdf/*.pdf`, and **native `.md`** files you maintain by hand.

---

## 2. Generated Markdown mirrors — pod-only for `.docx` workflows

- For each category, the runtime **prefers** indexed content under `data/documents_md/<category>/**/*.md` **when** that folder yields at least one non-empty, tokenizable file.
- **Operational practice on RunPod:** ingesting or converting **Word** procedures often produces a **generated** `documents_md/...` tree that exists on the **GPU pod** (large, regenerated), not necessarily in git.
- **`.md` files you place under `data/documents/<category>/` stay in place** as sources; the loader’s priority rules are implemented in `core/documents.py` (Markdown → txt → docx/pdf fallthrough when MD is empty or unusable).

In short: **`.docx` → often mirrored or built into `documents_md` on the server; hand-authored `.md` lives under `data/documents/` (per category) and is not moved by that workflow.**

---

## 3. What is versioned vs ignored

- `.gitignore` excludes **`data/documents/`** and **`data/documents_md/`** by default so bulk corpora are not committed accidentally.
- A **`data/documents/procedures/`** snapshot may be **force-added** when you want the repo to carry a reference corpus for local dev or review (optional).

---

## 4. Restoring `procedures` from the pod (when `scp` fails)

RunPod’s gateway often blocks **`scp`** and **non-interactive SSH exec**. Use the repo script (PTY + base64 stream):

```powershell
cd path\to\gemma-test
python scripts/fetch_pod_tar.py
```

Alternate path (backup clone on the pod):

```powershell
python scripts/fetch_pod_tar.py --remote /workspace/gemma-test-backup-202605051228/data/documents/procedures
```

Edit `HOST` / `USER` in `scripts/fetch_pod_tar.py` and `scripts/deploy_runner.py` if your RunPod SSH identity changes.

**Note:** Extracting this archive on **Windows** can normalize **Unicode** characters in filenames (accents may become stripped or substituted). The **`.docx` contents are unchanged**; if you need exact names in git, extract or `git add` from Linux/WSL, or treat the pod as source of truth for display names.

---

## 5. Example categories

| Folder | Role |
|--------|------|
| `data/documents/procedures/` | SENDIT SOPs (`.docx` typical on pod) |
| `data/documents/help_md/` | Help-center style articles (often `.md`) |

Categories are **organizational**; retrieval scope is controlled by the API/client (e.g. **all categories** when no `category` is sent).

---

## 6. Admin uploads

Staff can upload/replace files via **`/admin`**; the running API reloads `DocStore` after changes. Large binaries should still be avoided in git—prefer pod storage and admin UI or scripted sync.

---

## 7. Screenshots referenced from Markdown (`/api/rag-media`)

Markdown under **`data/documents_md/<category>/`** can embed UI captures as **`![](chemin/relatif.png)`** next to procedural text. The SPA loads them via **`GET /api/rag-media/<path>`**, where **`path`** is resolved **relative to the `data/documents_md` root** (FastAPI **`StaticFiles`** mount in `api/main.py`).

- **Operational rule:** Store **`.png`** / **`.webp`** / etc. beside the referencing **`.md`** file or in a subdirectory of the same category tree so the excerpt path resolves to an on-disk file.
- **Converted `.docx`:** If pipelines emit Markdown that points at `./media/image1.png`, those files must exist under the mirrored tree on the pod; otherwise the reply may show Alt text only or a broken `<img>` (same as any missing static asset).
- **Sizing:** Prefer reasonable resolution; **`data:`** URIs inside sources are stripped for the LLM context by **`core/sop_text_clean.py`** so prompts stay bounded.

Related: [`ARCHITECTURE.md`](ARCHITECTURE.md) §7.2 (« où cliquer »).

---

## 8. Procedure logigrammes (Mermaid sidecars)

Confirmed flowcharts live beside the corpus as **sidecar files**, not inside the Word/MD tree:

```
data/logigrammes/procedures/<stem>.mmd
```

- **Key:** `(category, stem)` — same as DocStore / document preview resolver.
- **Created via:** `/admin` Documents → **Créer / Modifier logigramme** (managers + administrators).
- **RAG:** On index load, when a sidecar exists, its Mermaid block is appended to the parent procedure text (see `core/logigrammes_store.py`, `core/documents.py`).
- **Preview:** Chat source modal tab **Logigramme** when `has_logigramme` is true.

See [`LOGIGRAMME.md`](LOGIGRAMME.md).
