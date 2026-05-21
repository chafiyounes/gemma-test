# Logigrammes (procedure flowcharts) — SSH evaluation only

**Status:** Experimental. **Not integrated in web_test or `/chat`** until format evaluation passes on the pod.

**Related:** [`ARCHITECTURE.md`](ARCHITECTURE.md), [`DATA_LAYOUT.md`](DATA_LAYOUT.md)

---

## Why SSH-only?

Before showing logigrammes in the chat UI, we must confirm that Gemma can **reliably** turn SENDIT procedures into valid diagram code. Evaluation runs on the RunPod via direct vLLM calls — no API or frontend changes.

---

## Formats under test

| Format | Output | Validator |
|--------|--------|-----------|
| **mermaid** | `flowchart TD` | Starts with `flowchart` / `graph` |
| **dot** | Graphviz `digraph { ... }` | Brace structure; optional `dot -Tsvg` |
| **plantuml** | `@startuml` … `@enduml` | Marker presence |
| **svg** | Minimal `<svg>` with rects/text | XML parse |
| **html** | `<div class="flow"><div class="step">…` | HTML markers |
| **json_graph** | `{"nodes":[],"edges":[]}` | JSON schema |

Implementation: [`core/logigramme_llm.py`](../core/logigramme_llm.py)

---

## Run evaluation (pod)

```bash
cd /workspace/gemma-test
python scripts/eval_logigramme_formats.py \
  --stems "Gestion des colis endommag_,Demande de remboursement - colis endommag_,Pr_paration des colis" \
  --trials 3 \
  --formats mermaid,dot,plantuml,svg,html,json_graph
```

Outputs:
- Artifacts: `outputs/logigramme_eval/<stem>_<format>_t<n>.<ext>`
- Reports: `outputs/logigramme_eval/report_<timestamp>.json` and `.md`

### Single-format prototype (Mermaid only)

```bash
python scripts/prototype_logigramme.py --stem "Gestion des colis endommag_"
```

---

## Scoring

### Automated (script)

1. **Syntax valid** (0/1) — parser/validator pass
2. **Structure count** — edges/steps/nodes ≥ 2
3. **Retry rate** — second prompt fired after invalid output
4. **Latency** — vLLM round-trip ms

### Manual (required before web integration)

Open saved artifacts. Score **fidelity** 1–5 per trial:
- Steps match the source procedure
- No invented branches or missing decision points
- Labels readable in French

Record scores in the report markdown or a follow-up note.

---

## Gate for web integration

Re-enable chat/UI only when **all** are true:

1. One format reaches **≥80% syntax valid** across 3 procedures × 3 trials
2. Manual fidelity **≥4/5** on at least 2 procedures for that format
3. Clear rendering path chosen (likely Mermaid or SVG)

Until then:
- No `mermaid` npm dependency in `web_test`
- No logigramme intent in [`core/llm.py`](../core/llm.py)
- No `generate_logigramme` agentic tool

---

## Reversibility

- Read-only on procedure corpus
- Outputs in `outputs/logigramme_eval/` (safe to delete)
- No database changes
