# Logigrammes (Mermaid flowcharts)

Generate **logigrammes** (procedure flowcharts) from SENDIT SOPs using Gemma via vLLM.

**Related:** [`ARCHITECTURE.md`](ARCHITECTURE.md), [`ROADMAP.md`](ROADMAP.md), [`DATA_LAYOUT.md`](DATA_LAYOUT.md).

---

## Overview

| Layer | Path | Role |
|-------|------|------|
| Core | `core/logigramme_llm.py` | Prompt, vLLM call, Mermaid validation, chat integration |
| Prototype CLI | `scripts/prototype_logigramme.py` | Direct pod test without chat UI |
| Agentic tool | `core/agentic_rag.py` | `generate_logigramme(document_id)` when agentic RAG is enabled |
| Chat UI | `web_test/src/components/MermaidDiagram.jsx` | Lazy-render ` ```mermaid ` blocks in bot messages |

---

## Prototype (pod)

Requires vLLM running and procedure corpus on the pod (`data/documents/procedures/` or generated `documents_md`).

```bash
cd /workspace/gemma-test
python scripts/prototype_logigramme.py --stem "Gestion des colis endommag_"
python scripts/prototype_logigramme.py --stem "Demande de remboursement - colis endommag_" --output outputs/logigrammes/remboursement.mmd
```

Output defaults to `outputs/logigrammes/<stem>.mmd`. Validate at [mermaid.live](https://mermaid.live).

---

## Chat triggers

**Classic RAG** (`POST /chat`): if the user message contains `logigramme`, `flowchart`, `diagramme`, or `diagram`, the API routes to `answer_logigramme()` before normal RAG. The response is a short intro plus a fenced Mermaid block (`flowchart TD` …).

**Agentic RAG:** tool `generate_logigramme` with parameter `document_id` (catalog id, e.g. `procedures/Gestion des colis endommag_`).

---

## Reversibility

- Logigramme generation is **read-only** on the corpus (no document writes).
- Prototype outputs go to `outputs/logigrammes/` (gitignored); safe to delete locally.
- No DB schema changes for v1.

---

## Quality checklist (manual)

1. Valid Mermaid syntax (starts with `flowchart TD` or `graph`).
2. Steps match the source procedure (no invented branches).
3. Node labels readable in French.
4. Chat UI renders the diagram; fallback shows raw code + Mermaid Live link on parse errors.
