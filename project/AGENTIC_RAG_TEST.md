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

## Gemma 4 + vLLM (research summary)

Gemma 4 instruct models use a **custom tool protocol** (special tokens such as `<|tool_call|>`, not plain JSON in the assistant string). vLLM exposes this through the **OpenAI-compatible** `/v1/chat/completions` API only if the server is started with the right flags and the **Gemma 4 tool chat template** (Jinja).

Official vLLM recipe (paraphrased):

- `--enable-auto-tool-choice` — required for automatic tool use.
- `--tool-call-parser gemma4` — maps Gemma’s native output to `message.tool_calls`.
- `--chat-template …/tool_chat_template_gemma4.jinja` — must be the vLLM example template (not the plain instruct template).

Optional: `--reasoning-parser gemma4` if you enable “thinking” / reasoning mode (`VLLM_GEMMA4_REASONING=1` in `scripts/start_vllm.sh`). Not required for text-only agentic RAG.

**This repo:** `scripts/start_vllm.sh` downloads the template into `scripts/vendor/` (when `TARGET=gemma4` and `VLLM_GEMMA4_TOOLING` is not `0`) and passes the three mandatory flags. If the download fails, agentic RAG will usually return answers **without** `tool_calls` until you fix the template path.

References:

- [Gemma 4 usage — Function calling / tool use](https://docs.vllm.ai/projects/recipes/en/latest/Google/Gemma4.html#function-calling-tool-use)
- [Tool calling (vLLM)](https://docs.vllm.ai/en/stable/features/tool_calling/)
- [gemma4_tool_parser](https://docs.vllm.ai/en/latest/api/vllm/tool_parsers/gemma4_tool_parser/)

## Full tests on the pod

From the pod (API + vLLM on localhost, or tunneled ports):

```bash
cd /workspace/gemma-test   # adjust
git pull
python scripts/bootstrap_agentic_map.py
# .env on pod: AGENTIC_RAG_ENABLED=true
bash scripts/start_vllm.sh gemma4    # picks up new tool flags after git pull
# restart FastAPI so .env is loaded
export ADMIN_PASSWORD='your-admin-password'
python scripts/test_agentic_rag_pod.py
```

The script checks, in order:

| Check | What it proves |
|--------|----------------|
| `vllm_health` | Port 8002 up |
| `vllm_models` | `VLLM_MODEL_NAME` is served |
| `vllm_tool_roundtrip` | **Critical:** model returns `tool_calls` for a trivial function (if this fails, fix vLLM flags/template before blaming the app) |
| `chat_agentic_unauth` | `/chat` without cookie → 401 |
| `api_agentic_e2e` | Admin cookie + French procedure question → `metadata.rag.mode=agentic_rag`, tool activity, timing |
| `api_agentic_darija` | Same pipeline, Arabizi/Darija-style question |
| `api_agentic_obscure` | Obscure query still returns 200 (refusal or weak match — behaviour may vary) |
| `api_agentic_user_forbidden` | If `USER_PASSWORD` set and `AGENTIC_RAG_ALLOW_NON_ADMIN=false`, expect 403 for user role |

Optional: `USER_PASSWORD=…` for the last check.

## Latency (“fast enough?”)

Expect **roughly 2–4×** the latency of a single naive-RAG completion for a typical flow:

1. One vLLM completion → `search_map` tool call  
2. Second completion → `fetch_procedure` (large context: full SOP text)  
3. Third completion → final user-facing answer  

Each hop is a full forward pass; `fetch_procedure` inflates prompt size (KV cache). For a 1–2 page SOP this is usually **seconds to low tens of seconds** on a 2× GPU MoE setup, not milliseconds. If you need sub-second retrieval, precomputed embeddings + vector DB (per the original spec) help the **map** step only; the **fetch** step is still one large prompt.

`AGENTIC_RAG_TEMPERATURE` (default **0.35** in settings) is lower than normal chat to stabilise tool selection.

## Edge cases (known)

| Case | Behaviour |
|------|-----------|
| Map JSON missing for category | User sees bootstrap message; no vLLM tool loop |
| vLLM without tool flags | Model may answer from parametric knowledge → **unsafe**; `test_agentic_rag_pod.py` catches this at `vllm_tool_roundtrip` |
| `DOCUMENT_NOT_FOUND` | Returned to model as tool result; should lead to refusal or second fetch |
| Parallel tool calls in one turn | Backend runs **`search_map` before `fetch_procedure`** to avoid fetch-without-query ordering bugs |
| Max 2 fetches | Enforced in `run_agentic_tool_loop`; further `fetch_procedure` calls get an error string |
| Non-admin + `agentic_rag` | 403 unless `AGENTIC_RAG_ALLOW_NON_ADMIN=true` |
| Heuristic map titles | Noisy table headers (`\| Titre \|`) can hurt BM25; production map should use LLM-generated French titles |

## Limitations / next steps

- **Map quality**: Replace `bootstrap_agentic_map.py` with the LLM map worker + e5 + Qdrant when you leave the “test track”.
- **Rollback**: `VLLM_GEMMA4_TOOLING=0` restores previous vLLM behaviour (no tool parser); `AGENTIC_RAG_ENABLED=false` disables the `/chat` branch.

Checkpoint label: **v1.0 — agentic-rag-darija** (see `core/agentic_rag.py`).
