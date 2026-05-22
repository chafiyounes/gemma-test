# Logigrammes (procedure flowcharts)

**Status:** Integrated for **procedures** only — admin/manager creation, RAG sidecar, preview tab. Normal chat is unchanged (no global logigramme intent).

**Related:** [`ARCHITECTURE.md`](ARCHITECTURE.md), [`DATA_LAYOUT.md`](DATA_LAYOUT.md)

---

## Format

**Mermaid** `flowchart TD` — chosen after pod eval (100% syntax valid across 3 procedures × 3 trials).

Implementation: [`core/logigramme_llm.py`](../core/logigramme_llm.py), [`core/logigramme_service.py`](../core/logigramme_service.py)

---

## Storage

Sidecar files keyed by `(category, stem)`:

```
data/logigrammes/procedures/<stem>.mmd
```

Module: [`core/logigrammes_store.py`](../core/logigrammes_store.py)

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

- Badge: **Logigramme ✓** or **Sans logigramme**
- Button: **Créer / Modifier logigramme** → modal with generate, refine chat, preview, **Enregistrer**

Auth: `_require_docs_manager` (gestionnaires + administrateurs).

API:

| Method | Path |
|--------|------|
| GET | `/api/admin/logigramme?category=procedures&stem=…` |
| POST | `/api/admin/logigramme/generate` |
| POST | `/api/admin/logigramme/save` |
| DELETE | `/api/admin/logigramme?category=procedures&stem=…` |

Generation uses dedicated admin endpoints — **not** `POST /chat`.

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
