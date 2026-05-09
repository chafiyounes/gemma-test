# Agentic RAG — test track

This repo implements an **optional** agentic RAG path aligned with the external spec
(agentic-rag-darija): a **procedure map** (`search_map`) plus **full-text fetch by id**
(`fetch_procedure`), driven by the LLM through OpenAI-style **tool calls** on vLLM.

It is **off by default** so production chat keeps the existing “inject DOCUMENTS DE RÉFÉRENCE” flow.

## What is implemented (test stack)

| Spec component | In this repo |
|----------------|--------------|
| Map index (e5 + Qdrant) | **BM25** on `title + tags` in JSON (per category) under `data/agentic_map/<category>.json` |
| Map worker (LLM per doc) | **`scripts/bootstrap_agentic_map.py`** — heuristic titles/tags (no API calls) |
| `search_map` / `fetch_procedure` | **`core/agentic_rag.py`** + `DocStore.get_document_by_stem` |
| Runtime system prompt | **`AGENTIC_SYSTEM_PROMPT`** in `core/agentic_rag.py` (matches COMPONENT 4) |
| Tool loop | **`run_agentic_tool_loop`** — requires vLLM (or compatible) **tool calling** |

## Enable

1. Build maps (after documents exist):

   ```bash
   python scripts/bootstrap_agentic_map.py
   ```

2. In `.env`:

   ```env
   AGENTIC_RAG_ENABLED=true
   ```

   Optional: allow non-admin testers:

   ```env
   AGENTIC_RAG_ALLOW_NON_ADMIN=true
   ```

3. Call **`POST /chat`** with JSON:

   ```json
   {
     "message": "كيفاش نبدل الرقم ديال الزبون فالليفريزون؟",
     "category": "procedures",
     "agentic_rag": true,
     "conversation_history": []
   }
   ```

   Only **admin** sessions may set `agentic_rag` unless `AGENTIC_RAG_ALLOW_NON_ADMIN=true`.

## Offline checks (no GPU)

```bash
python scripts/test_agentic_rag_smoke.py procedures "livraison téléphone"
```

## Limitations / next steps

- **Tool calling**: If the served model does not emit `tool_calls`, the assistant may answer without tools — responses are then unreliable; check vLLM logs and model/tool support.
- **Map quality**: Heuristic bootstrap is for wiring tests; production should use the LLM map worker + vector index from the full prompt.
- **Rollback**: Set `AGENTIC_RAG_ENABLED=false` or omit `agentic_rag` on `/chat` to use classic RAG only.

Checkpoint label: **v1.0 — agentic-rag-darija** (see `core/agentic_rag.py`).
