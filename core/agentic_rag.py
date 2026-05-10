"""Agentic RAG test harness (procedure map + tool loop).

Spec source: external build prompt « agentic-rag-darija ».

- **Map**: JSON per category under ``data/agentic_map/<category>.json`` —
  entries ``{id, title, tags[], category}`` (prefer LLM extraction: ``bootstrap_agentic_map.py --llm``).
- **search_map**: ``multilingual-e5-large`` cosine on ``title + tags`` when index exists
  (``scripts/build_agentic_embedding_index.py``); else BM25 over the same strings.
- **fetch_procedure**: deterministic lookup by document stem in :class:`core.documents.DocStore`.

Runtime UX: only the final assistant message is returned; tool traffic stays server-side.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections import Counter

import httpx
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app_config.settings import settings

from core.agentic_embeddings import (
    cosine_top_k,
    embed_query,
    load_embedding_index,
)
from core.documents import (
    REPO_ROOT,
    CategoryIndex,
    Doc,
    DocStore,
    _tokenize,
    expand_query_for_retrieval_fr_darija,
    get_store,
)

logger = logging.getLogger(__name__)

_VLLM_CONNECT_RETRIES = 4
_VLLM_CONNECT_RETRY_DELAY_S = 15.0


async def _post_chat_completions_with_retries(client: Any, payload: Dict[str, Any]) -> Any:
    last_exc: Optional[Exception] = None
    for attempt in range(_VLLM_CONNECT_RETRIES):
        try:
            resp = await client.post("/v1/chat/completions", json=payload)
            resp.raise_for_status()
            return resp
        except httpx.ConnectError as exc:
            last_exc = exc
            if attempt + 1 < _VLLM_CONNECT_RETRIES:
                logger.warning(
                    "vLLM unreachable during agentic loop (attempt %s/%s)",
                    attempt + 1,
                    _VLLM_CONNECT_RETRIES,
                )
                await asyncio.sleep(_VLLM_CONNECT_RETRY_DELAY_S)
    assert last_exc is not None
    raise last_exc

# COMMIT: v1.0 — agentic-rag-darija (aligned with build prompt COMPONENT 4)
AGENTIC_SYSTEM_PROMPT = """
# COMMIT: v1.0 — agentic-rag-darija

You are a precise assistant for an internal procedure knowledge base.
Documents are written in French. Users may write in French, Darija
(Arabic or Arabizi script), or a mix of both.

Your job: find and return the correct procedure using your tools.
Never answer a procedure question from memory. Always use your tools.

TOOLS AVAILABLE:

search_map(query)
  Search the procedure index. Always call this first.
  Translate the user query to French before calling if needed.
  Returns up to 5 candidate procedures.

fetch_procedure(id)
  Fetch the full procedure by ID.
  Call this after search_map identifies a strong candidate.
  Fetch at most 2 documents per user query.

STEP BY STEP:

1. Identify the language of the user query.
   If Darija, internally translate the intent to French. Never show this to the user.

2. Call search_map() with a short French query.
   Read the returned titles. Does one clearly match the user's intent?

3. Call fetch_procedure() on the best match.
   Read the full procedure. Does it answer the question?

4a. If yes:
    Respond in the same language the user wrote in.
    Summarize the procedure accurately. Do not invent or add steps.
    End with the procedure title as a reference.

4b. If no match after 2 fetches:
    Do not guess. Respond:
    French: "Je n'ai pas trouvé de procédure correspondante."
    Darija: adapt to the user's script and dialect naturally.
    Suggest they rephrase or contact support.

HARD RULES:
- Never expose tool names, IDs, or map structure to the user
- Never fetch more than 2 documents per query
- Never hallucinate a procedure that was not retrieved
- Always respond in the user's language
""".strip()


_MAP_ENTRY_CATEGORIES = frozenset(
    {"compte", "sécurité", "accès", "facturation", "technique", "autre"}
)


@dataclass
class MapEntry:
    id: str
    title: str
    tags: List[str]
    category: str

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "title": self.title, "tags": list(self.tags), "category": self.category}


def map_json_path(category: str) -> Path:
    base = Path(settings.AGENTIC_RAG_MAP_DIR)
    if not base.is_absolute():
        base = REPO_ROOT / base
    return base / f"{category}.json"


def load_map_entries(category: str) -> List[MapEntry]:
    path = map_json_path(category)
    if not path.is_file():
        logger.warning("Agentic map missing: %s", path)
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.error("Agentic map invalid JSON %s: %s", path, exc)
        return []
    if not isinstance(raw, list):
        return []
    out: List[MapEntry] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        eid = str(item.get("id", "")).strip()
        title = str(item.get("title", "")).strip()
        tags_raw = item.get("tags") or []
        tags = [str(t).strip() for t in tags_raw if str(t).strip()][:12]
        cat = str(item.get("category", "autre")).strip().lower()
        if cat not in _MAP_ENTRY_CATEGORIES:
            cat = "autre"
        if eid and title:
            out.append(MapEntry(id=eid, title=title, tags=tags, category=cat))
    return out


def _entries_to_category_index(entries: List[MapEntry]) -> CategoryIndex:
    docs: List[Doc] = []
    df: Counter = Counter()
    total_len = 0
    for e in entries:
        blob = f"{e.title} {' '.join(e.tags)}"
        toks = _tokenize(blob)
        if not toks:
            toks = _tokenize(e.id.replace("_", " "))
        if not toks:
            continue
        tf = Counter(toks)
        for term in tf:
            df[term] += 1
        docs.append(
            Doc(name=e.id, category="", text=blob, tokens=toks, tf=tf)
        )
        total_len += len(toks)
    avgdl = total_len / len(docs) if docs else 1.0
    return CategoryIndex(name="__agentic_map__", docs=docs, df=df, avgdl=avgdl)


def _bm25_score(
    store: DocStore,
    q_tokens: List[str],
    doc: Doc,
    idx: CategoryIndex,
    *,
    k1: float = 1.5,
    b: float = 0.75,
) -> float:
    return store._bm25(q_tokens, doc, idx, k1=k1, b=b)  # type: ignore[attr-defined]


def _search_map_embeddings(
    category: str,
    query: str,
    entries: List[MapEntry],
    *,
    k: int,
) -> Optional[List[Dict[str, Any]]]:
    """Return results or None to signal fallback to BM25."""
    if not settings.AGENTIC_RAG_USE_EMBEDDINGS:
        return None
    loaded = load_embedding_index(category)
    if loaded is None:
        logger.debug("No embedding index for category=%s", category)
        return None
    emb, idx_ids = loaded
    entry_by_id = {e.id: e for e in entries}
    if len(idx_ids) != len(entries) or set(idx_ids) != set(entry_by_id.keys()):
        logger.warning(
            "Embedding index out of sync with map JSON for %s — rebuild with "
            "scripts/build_agentic_embedding_index.py",
            category,
        )
        return None
    qv = embed_query(query)
    if qv is None:
        return None
    ranked = cosine_top_k(qv, emb, idx_ids, k=k)
    if not ranked:
        return []
    thr = float(settings.AGENTIC_RAG_MAP_CONFIDENCE_THRESHOLD)
    out: List[Dict[str, Any]] = []
    for rank, (eid, score) in enumerate(ranked):
        e = entry_by_id.get(eid)
        if not e:
            continue
        row: Dict[str, Any] = {
            "id": e.id,
            "title": e.title,
            "tags": e.tags,
            "category": e.category,
        }
        if rank == 0 and score < thr:
            row["low_confidence"] = True
        out.append(row)
    return out


def search_map(
    store: DocStore,
    query: str,
    entries: List[MapEntry],
    *,
    category: str = "",
    k: int = 5,
    expand_fr_darija_hints: bool = True,
) -> List[Dict[str, Any]]:
    """Return up to *k* map rows: e5+cosine when index exists, else BM25."""
    if not entries:
        return []
    q_raw = (query or "").strip()
    q = expand_query_for_retrieval_fr_darija(q_raw) if expand_fr_darija_hints else q_raw

    if category:
        emb_results = _search_map_embeddings(category, q, entries, k=k)
        if emb_results is not None:
            logger.info("search_map: multilingual-e5 index (%s, k=%s)", category, k)
            return emb_results

    idx = _entries_to_category_index(entries)
    logger.info("search_map: BM25 fallback (%s)", category or "?")
    if not idx.docs:
        return []

    q_tokens = _tokenize(q)
    scored: List[Tuple[float, MapEntry]] = []
    entry_by_id = {e.id: e for e in entries}
    for d in idx.docs:
        e = entry_by_id.get(d.name)
        if not e:
            continue
        s = _bm25_score(store, q_tokens, d, idx) if q_tokens else 0.0
        scored.append((s, e))

    scored.sort(key=lambda x: x[0], reverse=True)
    if q_tokens and not any(s > 0 for s, _ in scored):
        for e in entries[:k]:
            scored.append((0.0, e))
        seen = set()
        deduped = []
        for s, e in scored:
            if e.id in seen:
                continue
            seen.add(e.id)
            deduped.append((s, e))
        scored = deduped[:k]
    else:
        scored = scored[:k]

    top_score = scored[0][0] if scored else 0.0
    out: List[Dict[str, Any]] = []
    for rank, (s, e) in enumerate(scored):
        row: Dict[str, Any] = {
            "id": e.id,
            "title": e.title,
            "tags": e.tags,
            "category": e.category,
        }
        # BM25 proxy for « cosine < 0.5 » on the best hit only
        if rank == 0 and top_score <= 0.0:
            row["low_confidence"] = True
        out.append(row)
    return out


def fetch_procedure(store: DocStore, category: str, proc_id: str) -> str:
    text = store.get_document_by_stem(category, proc_id.strip())
    if text is None:
        return "DOCUMENT_NOT_FOUND"
    return text


SEARCH_MAP_TOOL = {
    "type": "function",
    "function": {
        "name": "search_map",
        "description": (
            "Search the procedure metadata index. Pass a short French query (one sentence). "
            "Returns up to 5 candidates with id, title, tags, category."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "French search query, one sentence",
                }
            },
            "required": ["query"],
        },
    },
}

FETCH_PROCEDURE_TOOL = {
    "type": "function",
    "function": {
        "name": "fetch_procedure",
        "description": (
            "Load the full procedure text by document id (same id as in search_map results)."
        ),
        "parameters": {
            "type": "object",
            "properties": {"id": {"type": "string", "description": "Procedure document id"}},
            "required": ["id"],
        },
    },
}


def retrieval_fallback_query(messages: List[Dict[str, Any]]) -> str:
    """Last user text if the model emitted search_map without a query."""
    for m in reversed(messages):
        if m.get("role") == "user" and m.get("content"):
            return str(m["content"])[:500]
    return "procédure"


def _parse_tool_args(arguments: Optional[str]) -> Dict[str, Any]:
    if not arguments or not str(arguments).strip():
        return {}
    try:
        return json.loads(arguments)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", str(arguments))
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
        return {}


async def run_agentic_tool_loop(
    *,
    client: Any,
    model_name: str,
    base_messages: List[Dict[str, Any]],
    category: str,
    max_tokens: int,
    temperature: float,
    top_p: float,
    max_rounds: int = 10,
    max_fetch: int = 2,
) -> Tuple[str, Dict[str, Any]]:
    """Call vLLM with OpenAI-style tools until assistant returns text or rounds exhausted."""
    store = get_store()
    entries = load_map_entries(category)
    meta: Dict[str, Any] = {
        "mode": "agentic_rag",
        "category": category,
        "map_entries": len(entries),
        "tool_rounds": 0,
        "fetch_count": 0,
        "context_chars": 0,
        "documents_in_prompt": 0,
    }
    if not entries:
        return (
            "⚠️ Mode agentic RAG : aucune carte de procédures pour cette catégorie. "
            "Exécutez `python scripts/bootstrap_agentic_map.py` puis réessayez.",
            meta,
        )

    messages = list(base_messages)
    fetch_count = 0

    for round_i in range(max_rounds):
        payload = {
            "model": model_name,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
            "tools": [SEARCH_MAP_TOOL, FETCH_PROCEDURE_TOOL],
            "tool_choice": "auto",
        }
        resp = await _post_chat_completions_with_retries(client, payload)
        data = resp.json()
        choice = data["choices"][0]
        msg = choice.get("message") or {}
        fr = choice.get("finish_reason")
        if fr:
            meta.setdefault("vllm_finish_reasons", []).append(fr)
        tool_calls = msg.get("tool_calls") or []

        if not tool_calls:
            text = (msg.get("content") or "").strip()
            meta["tool_rounds"] = round_i
            if not text:
                return (
                    "⚠️ Le modèle n'a renvoyé ni outils ni texte. "
                    "Vérifiez la prise en charge des appels d'outils côté vLLM.",
                    meta,
                )
            return text, meta

        meta["tool_rounds"] = round_i + 1
        messages.append(
            {
                "role": "assistant",
                "content": msg.get("content"),
                "tool_calls": tool_calls,
            }
        )

        # If the model emits parallel calls, run map search before fetch_procedure.
        def _tc_sort_key(tc: Dict[str, Any]) -> int:
            fn = tc.get("function") or {}
            n = fn.get("name") or ""
            return 0 if n == "search_map" else 1

        for tc in sorted(tool_calls, key=_tc_sort_key):
            tid = tc.get("id") or f"call_{round_i}"
            fn = (tc.get("function") or {})
            name = fn.get("name") or ""
            args = _parse_tool_args(fn.get("arguments"))

            if name == "search_map":
                q = str(args.get("query", "")).strip() or retrieval_fallback_query(messages)
                results = search_map(store, q, entries, category=category, k=5)
                content = json.dumps(results, ensure_ascii=False)
            elif name == "fetch_procedure":
                pid = str(args.get("id", "")).strip()
                if fetch_count >= max_fetch:
                    content = (
                        "ERROR: Maximum procedure fetches reached for this query (2). "
                        "Pick from search_map results or refuse."
                    )
                else:
                    fetch_count += 1
                    content = fetch_procedure(store, category, pid)
                    if content != "DOCUMENT_NOT_FOUND":
                        meta["context_chars"] = meta.get("context_chars", 0) + len(content)
                        meta["documents_in_prompt"] = int(meta.get("documents_in_prompt", 0)) + 1
            else:
                content = json.dumps({"error": f"unknown_tool:{name}"})

            messages.append({"role": "tool", "tool_call_id": tid, "content": content})

        meta["fetch_count"] = fetch_count

    return (
        "⚠️ Limite d'étapes agentic atteinte. Reformulez la question ou contactez le support.",
        meta,
    )
