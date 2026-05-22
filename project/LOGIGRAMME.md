# Logigrammes (procedure flowcharts)

**Status:** Integrated for **procedures** — admin/manager creation, RAG sidecar, document preview tab, and **explicit-request** logigrammes in normal chat.

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
data/logigrammes/procedures/<stem>.mmd                        # published (chat + RAG, shared)
data/logigrammes/procedures/drafts/<user_slug>/<stem>.mmd     # per-user admin draft
```

Module: [`core/logigrammes_store.py`](../core/logigrammes_store.py)

Only **published** `.mmd` files are merged into RAG. Drafts are per logged-in user (session username) and are not visible in chat/RAG until published.

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

- Button: **Créer / Modifier logigramme** → modal with generate, refine, editable Mermaid, live preview, **Publier** (confirmation)
- Badge: **Publié ✓** / **Brouillon** (your draft only) / **Sans logigramme**

Auth: `_require_docs_manager` (gestionnaires + administrateurs). Draft paths use the session username server-side.

API:

| Method | Path |
|--------|------|
| GET | `/api/admin/logigramme?category=procedures&stem=…` |
| POST | `/api/admin/logigramme/generate` |
| POST | `/api/admin/logigramme/draft` |
| POST | `/api/admin/logigramme/save` |
| DELETE | `/api/admin/logigramme?category=procedures&stem=…` |

Generation uses dedicated admin endpoints — **not** `POST /chat`.

**Générer** reads the procedure automatically. **Affiner** is optional. The **Code Mermaid** textarea is editable with **real-time preview** (250 ms debounce). Invalid syntax keeps the last good render.

- **Auto-save** — edits are saved to your draft (~1.5 s debounce); no manual draft button
- **Annuler modifications** — restores your last auto-saved draft; clears Affiner input/history
- **Publier** — sole explicit save to the shared `.mmd`; confirms overwrite when a published version already exists; reloads RAG; visible in chat preview
- **Télécharger PNG** — export the current preview as PNG (client-side, no server dependency)
- Close modal via **×** (draft already auto-saved)

Preview: **double-clic** zooms in on the click area; double-clic again resets. Scroll when the diagram is taller than the panel or when zoomed.

Goal: the diagram alone should let an operator follow the **entire** procedure (all steps, branches, lists). Generation prompts enforce exhaustive coverage; **Affiner** fixes gaps.

Validation: [`core/mermaid_validate.py`](../core/mermaid_validate.py)

---

## Chat (explicit logigramme request)

When the user **explicitly** asks for a logigramme (keywords: *logigramme*, *diagramme de flux*, *schéma du processus*, *flowchart*, etc.), `POST /chat` may attach a diagram after the textual answer.

Module: [`core/chat_logigramme.py`](../core/chat_logigramme.py)

Flow:

1. RAG + LLM answer with numbered steps for the situation (no Mermaid in the text).
2. If a **published** sidecar matches the primary retrieved procedure → reuse it (`source: "published"`).
3. Else generate a **situational** Mermaid from procedure context + user question + step answer (`source: "generated"`).
4. Response metadata includes `logigramme: { mermaid, stem, source }`.

UI: [`MessageBubble.jsx`](../web_test/src/components/MessageBubble.jsx) renders the diagram below the text (lazy `MermaidDiagram`) with **Télécharger PNG**.

Generic questions without logigramme keywords are unchanged.

---

## Document preview (Source click)

When a user clicks a **Source** hint, [`DocumentPreviewModal`](../web_test/src/components/DocumentPreviewModal.jsx) shows tabs:

**Word | Markdown | Logigramme** (Logigramme tab only when a sidecar exists).

Mermaid in chat message bodies is only for explicit logigramme requests — not inline in arbitrary assistant prose.

---

## Pod evaluation (reference)

Multi-format eval (May 2026): mermaid/dot/plantuml/html/json_graph at 100% syntax; svg 33%.

Report on pod: `outputs/logigramme_eval/report_20260521T163814Z.json`

Scripts: [`scripts/eval_logigramme_formats.py`](../scripts/eval_logigramme_formats.py), [`scripts/prototype_logigramme.py`](../scripts/prototype_logigramme.py)

---

## Safety boundaries

- Logigramme intent is **not** in [`core/llm.py`](../core/llm.py) `SYSTEM_PROMPT` — only [`core/chat_logigramme.py`](../core/chat_logigramme.py) after an explicit user keyword
- No `generate_logigramme` agentic tool
- No Mermaid parsing in [`messageFormat.jsx`](../web_test/src/lib/messageFormat.jsx) — diagrams come from `metadata.logigramme` only
