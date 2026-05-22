# Logigrammes (procedure flowcharts)

**Status:** Integrated for **procedures** only — admin/manager creation, RAG sidecar, preview tab. Normal chat is unchanged (no global logigramme intent).

**Related:** [`ARCHITECTURE.md`](ARCHITECTURE.md), [`DATA_LAYOUT.md`](DATA_LAYOUT.md)

---

## Format

**Mermaid** `flowchart TD` with **subgraph swimlanes** per SENDIT actor present in the procedure (Magasinier, Système Sendit, Chauffeur, Stock, Service Qualité, etc.) — not every lane, only those mentioned in the SOP.

Existing sidecars saved before this layout: **regenerate or Affiner** in admin to get swimlanes.

Implementation: [`core/logigramme_llm.py`](../core/logigramme_llm.py), [`core/logigramme_service.py`](../core/logigramme_service.py)

---

## Storage

Sidecar files keyed by `(category, stem)`:

```
data/logigrammes/procedures/<stem>.mmd          # published (chat + RAG)
data/logigrammes/procedures/<stem>.draft.mmd    # admin draft only
```

Module: [`core/logigrammes_store.py`](../core/logigrammes_store.py)

Only **published** `.mmd` files are merged into RAG. Drafts are for continuing work in admin.

On DocStore load, when a sidecar exists, the procedure text is augmented with:

```markdown
## Logigramme (flowchart)
```mermaid
...
```
```

So RAG can retrieve diagram content with the parent procedure — without a separate chat hook.

---

## Admin / manager workflow

On **Documents** (`/admin`), each row in the **procedures** category shows:

- Button: **Créer / Modifier logigramme** → modal with generate, refine, editable Mermaid, **Enregistrer brouillon**, **Publier** (confirmation)
- Badge: **Publié ✓** / **Brouillon** / **Sans logigramme**

Auth: `_require_docs_manager` (gestionnaires + administrateurs).

API:

| Method | Path |
|--------|------|
| GET | `/api/admin/logigramme?category=procedures&stem=…` |
| POST | `/api/admin/logigramme/generate` |
| POST | `/api/admin/logigramme/draft` |
| POST | `/api/admin/logigramme/save` |
| DELETE | `/api/admin/logigramme?category=procedures&stem=…` |

Generation uses dedicated admin endpoints — **not** `POST /chat`.

**Générer** reads the procedure automatically. **Affiner** is optional. The **Code Mermaid** textarea is editable.

- **Enregistrer brouillon** — saves `.draft.mmd` (admin only; not in chat/RAG)
- **Publier** — confirms, then saves `.mmd`, reloads RAG, visible in chat preview

Goal: the diagram alone should let an operator follow the **entire** procedure (all steps, branches, lists). Generation prompts enforce exhaustive coverage; **Affiner** fixes gaps.

Validation: [`core/mermaid_validate.py`](../core/mermaid_validate.py)

---

## Chat preview

When a user clicks a **Source** hint, [`DocumentPreviewModal`](../web_test/src/components/DocumentPreviewModal.jsx) shows tabs:

**Word | Markdown | Logigramme** (Logigramme tab only when a sidecar exists).

Mermaid renders only in the preview modal (lazy-loaded) — not in chat message bodies.

---

## Pod evaluation (reference)

Multi-format eval (May 2026): mermaid/dot/plantuml/html/json_graph at 100% syntax; svg 33%.

Report on pod: `outputs/logigramme_eval/report_20260521T163814Z.json`

Scripts: [`scripts/eval_logigramme_formats.py`](../scripts/eval_logigramme_formats.py), [`scripts/prototype_logigramme.py`](../scripts/prototype_logigramme.py)

---

## Explicit non-goals (normal chat safety)

- No logigramme intent in [`core/llm.py`](../core/llm.py)
- No `generate_logigramme` agentic tool
- No Mermaid rendering in [`messageFormat.jsx`](../web_test/src/lib/messageFormat.jsx)
