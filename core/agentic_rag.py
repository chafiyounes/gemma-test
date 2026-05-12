"""Agentic RAG with runtime doc catalog and iterative document requests."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app_config.settings import settings

from core.documents import (
    DOCS_DIR,
    DOCS_MD_DIR,
    DOCS_TXT_DIR,
    DocStore,
    _best_window_for_query,
    _greedy_inject_document_blocks,
    condense_sop_plaintext,
    get_store,
)

logger = logging.getLogger(__name__)

_VLLM_CONNECT_RETRIES = 4
_VLLM_CONNECT_RETRY_DELAY_S = 15.0

AGENTIC_NOT_FOUND = "Je n'ai pas trouvé la réponse dans les documents disponibles."

AGENTIC_SYSTEM_PROMPT_TEMPLATE = """
You are a precise assistant for an internal procedure knowledge base.
Documents are in French. Users may write in French, Darija (Arabic/Arabizi), or mixed.

You MUST answer ONLY from retrieved documents. Never answer from memory.

You have one tool:
- request_documents(ids: string[])
  It returns full text chunks for the requested document IDs.

Workflow rules:
1) Read the document catalog below (each row has id, path, objective, section_1).
2) Pick the most relevant IDs using objective and section_1.
3) Call request_documents with **1–{max_ids_round}** IDs per call (aim for **~{target_docs}** distinct procedures total when helpful, **up to {max_total}** unique ids across all rounds).
4) If retrieved docs are insufficient, or the loaded bodies look like the **wrong** procedure while **other** catalog rows remain plausible, call request_documents again with **different** IDs.
5) Max **{max_rounds}** tool rounds total. If still insufficient, answer exactly with:
   "{not_found}"
6) Final answer must be in the same language style as the user.
7) Never expose internal tool details or catalog internals to the user.

Document catalog (JSON):
{catalog_json}
""".strip()

# English router prompt: select documents only; answering happens in a second model call.
AGENTIC_ROUTER_SYSTEM_PROMPT_TEMPLATE = """
You are a **retrieval router** for the SENDIT internal procedure knowledge base (Morocco logistics).
Procedure texts are mostly in French; user questions may be French, Darija (Arabizi), English, or mixed.

**Your only job in this step** is to choose which catalog entries to load with the tool. Do **not**
answer the user’s question and do **not** summarize procedures in this step. If you output plain text
without calling `request_documents` when documents might help, you fail the task.

Tool:
- `request_documents(ids: string[])` — returns the **full** text body for each document `id` listed in the catalog.

Rules:
1) Read the JSON catalog. Each item has: `id`, `path`, `objective` (procedure goal when detected), `section_1` (first section slice).
2) Pick **1–{max_ids_round}** ids per tool call that are most likely to contain evidence for the **latest user message** (use conversation history only for disambiguation).
3) Call `request_documents` with those ids. Aim for **~{target_docs}** relevant documents when the question needs it, **up to {max_total}** unique ids loaded in total across rounds.
4) If results look **off-topic** but **other** catalog rows could still hold the answer, you **must** call `request_documents` again in a later round with different ids (max **{max_rounds}** tool rounds total).
5) Stop calling tools when you have enough sources or when no catalog entry plausibly matches. You may output a short neutral line like "OK" before stopping **only after** you have finished all needed tool calls; the system will **ignore** free-text and use tool payloads only.

Catalog (JSON):
{catalog_json}
""".strip()


@dataclass
class MapEntry:
    id: str
    path: str
    objective: str
    section_1: str

    def to_dict(self) -> Dict[str, str]:
        return {
            "id": self.id,
            "path": self.path,
            "objective": self.objective,
            "section_1": self.section_1,
        }


def _extract_objective(text: str, max_chars: int = 360) -> str:
    if not text:
        return ""
    t = text.replace("\r\n", "\n").replace("\r", "\n")
    m = re.search(
        r"(?im)^\s*(?:#+\s*)?(?:\* *)?(objectif|objective)(?:\* *)?\s*[:\-–]\s*(.+?)\s*$",
        t[:8000],
    )
    if not m:
        return ""
    body = re.sub(r"\s+", " ", (m.group(2) or "").strip())
    return body[:max_chars] if body else ""


def _extract_section_1(text: str, max_chars: int = 420) -> str:
    if not text:
        return ""
    t = text.replace("\r\n", "\n").replace("\r", "\n")
    sec1 = re.search(r"(?im)^(?:#+\s*)?(?:section|partie)?\s*1[\.\):\-\s].*$", t)
    sec2 = re.search(r"(?im)^(?:#+\s*)?(?:section|partie)?\s*2[\.\):\-\s].*$", t)
    if sec1:
        start = sec1.start()
        end = sec2.start() if sec2 and sec2.start() > start else min(len(t), start + 1400)
        chunk = t[start:end]
    else:
        chunk = t[:1400]
    chunk = re.sub(r"\s+", " ", chunk).strip()
    return chunk[:max_chars]


def _resolve_doc_path(category: str, stem: str) -> str:
    root = Path(__file__).resolve().parent.parent
    candidates = [
        DOCS_MD_DIR / category / f"{stem}.md",
        DOCS_TXT_DIR / category / f"{stem}.txt",
        DOCS_DIR / category / f"{stem}.docx",
        DOCS_DIR / category / f"{stem}.pdf",
    ]
    for p in candidates:
        if p.is_file():
            try:
                return str(p.relative_to(root))
            except Exception:
                return str(p)
    if "/" in stem or "\\" in stem:
        return f"data/documents/{category}/{stem.replace(chr(92), '/')}.pdf"
    return f"data/documents/{category}/{stem}"


def build_document_catalog(store: DocStore, category: str) -> List[MapEntry]:
    idx = store.indexes.get(category)
    if not idx:
        return []
    rows: List[MapEntry] = []
    for d in idx.docs:
        rows.append(
            MapEntry(
                id=d.name,
                path=_resolve_doc_path(category, d.name),
                objective=_extract_objective(d.text),
                section_1=_extract_section_1(d.text),
            )
        )
    return rows


def _router_prompt_limits() -> tuple[int, int, int, int]:
    """(per_round_cap, max_total, max_rounds, target_docs) from settings."""
    max_total = max(1, settings.AGENTIC_RAG_ROUTER_MAX_TOTAL_IDS)
    per_round = max(
        1,
        min(settings.AGENTIC_RAG_ROUTER_MAX_IDS_PER_ROUND, max_total),
    )
    rounds = max(1, settings.AGENTIC_RAG_ROUTER_MAX_ROUNDS)
    target = max(1, min(settings.AGENTIC_RAG_ROUTER_TARGET_DOCS, max_total))
    return per_round, max_total, rounds, target


def make_agentic_system_prompt(catalog: List[MapEntry]) -> str:
    catalog_json = json.dumps([r.to_dict() for r in catalog], ensure_ascii=False, indent=2)
    per_round, max_total, rounds, target = _router_prompt_limits()
    return AGENTIC_SYSTEM_PROMPT_TEMPLATE.format(
        not_found=AGENTIC_NOT_FOUND,
        catalog_json=catalog_json,
        max_ids_round=per_round,
        max_total=max_total,
        max_rounds=rounds,
        target_docs=target,
    )


def make_router_system_prompt(catalog: List[MapEntry]) -> str:
    catalog_json = json.dumps([r.to_dict() for r in catalog], ensure_ascii=False, indent=2)
    per_round, max_total, rounds, target = _router_prompt_limits()
    return AGENTIC_ROUTER_SYSTEM_PROMPT_TEMPLATE.format(
        catalog_json=catalog_json,
        max_ids_round=per_round,
        max_rounds=rounds,
        max_total=max_total,
        target_docs=target,
    )


def format_retrieved_documents_for_prompt(
    *,
    category: str,
    id_to_text: Dict[str, str],
    ordered_ids: List[str],
    max_chars: int,
    condense: bool,
    anchor_query: str = "",
    expand_fr_darija_hints: bool = False,
) -> str:
    q = (anchor_query or "").strip()
    entries: List[tuple[str, str]] = []
    for doc_id in ordered_ids:
        txt = id_to_text.get(doc_id)
        if not txt:
            continue
        body = condense_sop_plaintext(txt) if condense else txt.strip()
        header = f"### Document : {doc_id}  (catégorie : {category})\n"
        entries.append((header, body))
    if settings.RAG_GREEDY_FULL_DOCS:
        blocks = _greedy_inject_document_blocks(
            entries,
            query=q,
            max_chars=max_chars,
            expand_fr_darija_hints=expand_fr_darija_hints,
        )
        return "\n".join(blocks)
    parts: List[str] = []
    budget = max_chars
    for header, body in entries:
        overhead = len(header) + 1
        if budget <= overhead + 80:
            break
        max_body = budget - overhead
        if len(body) <= max_body:
            block = header + body + "\n"
        else:
            excerpt = _best_window_for_query(
                body,
                q or "",
                max_body,
                expand_fr_darija_hints=expand_fr_darija_hints,
            )
            block = header + excerpt + "\n"
        parts.append(block)
        budget -= len(block)
        if budget <= 0:
            break
    return "\n".join(parts)


REQUEST_DOCUMENTS_TOOL = {
    "type": "function",
    "function": {
        "name": "request_documents",
        "description": "Request full text for one or more document ids from the catalog.",
        "parameters": {
            "type": "object",
            "properties": {
                "ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of document IDs to retrieve",
                }
            },
            "required": ["ids"],
        },
    },
}


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


def _request_documents(
    store: DocStore,
    category: str,
    ids: List[str],
    *,
    max_ids_per_round: int,
) -> Dict[str, Any]:
    if max_ids_per_round <= 0:
        clean = [str(x).strip() for x in ids if str(x).strip()]
        return {"found": [], "not_found": clean}
    unique_ids: List[str] = []
    for raw in ids:
        doc_id = str(raw or "").strip()
        if not doc_id or doc_id in unique_ids:
            continue
        unique_ids.append(doc_id)
        if len(unique_ids) >= max_ids_per_round:
            break

    found: List[Dict[str, str]] = []
    not_found: List[str] = []
    for doc_id in unique_ids:
        txt = store.get_document_by_stem(category, doc_id)
        if txt is None:
            not_found.append(doc_id)
            continue
        found.append({"id": doc_id, "content": txt})
    return {"found": found, "not_found": not_found}


async def _post_chat_completions_with_retries(client: Any, payload: Dict[str, Any]) -> Any:
    last_exc: Optional[Exception] = None
    for attempt in range(_VLLM_CONNECT_RETRIES):
        try:
            resp = await client.post("/v1/chat/completions", json=payload)
            if resp.status_code in (429, 502, 503) and attempt + 1 < _VLLM_CONNECT_RETRIES:
                await asyncio.sleep(min(5.0 * (attempt + 1), 45.0))
                continue
            resp.raise_for_status()
            return resp
        except httpx.HTTPStatusError as exc:
            if (exc.response.status_code if exc.response is not None else 0) in (429, 502, 503):
                if attempt + 1 < _VLLM_CONNECT_RETRIES:
                    await asyncio.sleep(min(5.0 * (attempt + 1), 45.0))
                    continue
            raise
        except httpx.ConnectError as exc:
            last_exc = exc
            if attempt + 1 < _VLLM_CONNECT_RETRIES:
                await asyncio.sleep(_VLLM_CONNECT_RETRY_DELAY_S)
                continue
            raise
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("vLLM request exhausted retries")


async def run_agentic_tool_loop(
    *,
    client: Any,
    model_name: str,
    base_messages: List[Dict[str, Any]],
    category: str,
    max_tokens: int,
    temperature: float,
    top_p: float,
    max_rounds: int = 3,
    max_ids_per_round: int = 3,
) -> Tuple[str, Dict[str, Any]]:
    store = get_store()
    meta: Dict[str, Any] = {
        "mode": "agentic_rag",
        "category": category,
        "tool_rounds": 0,
        "context_chars": 0,
        "documents_in_prompt": 0,
    }
    messages = list(base_messages)

    for round_i in range(max_rounds):
        payload = {
            "model": model_name,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
            "tools": [REQUEST_DOCUMENTS_TOOL],
            "tool_choice": "auto",
        }
        resp = await _post_chat_completions_with_retries(client, payload)
        data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            return "⚠️ Réponse vide du serveur d'inférence.", {**meta, "note": "vllm_empty_choices"}
        choice = choices[0]
        msg = choice.get("message") or {}
        tool_calls = msg.get("tool_calls") or []

        if not tool_calls:
            text = (msg.get("content") or "").strip()
            if not text:
                return AGENTIC_NOT_FOUND, meta
            meta["tool_rounds"] = round_i
            return text, meta

        meta["tool_rounds"] = round_i + 1
        messages.append(
            {"role": "assistant", "content": msg.get("content"), "tool_calls": tool_calls}
        )

        for tc in tool_calls:
            tid = tc.get("id") or f"call_{round_i}"
            fn = tc.get("function") or {}
            name = fn.get("name") or ""
            args = _parse_tool_args(fn.get("arguments"))
            if name != "request_documents":
                content = json.dumps({"error": f"unknown_tool:{name}"}, ensure_ascii=False)
            else:
                ids = args.get("ids") or []
                if not isinstance(ids, list):
                    ids = [str(ids)]
                result = _request_documents(
                    store,
                    category,
                    [str(x) for x in ids],
                    max_ids_per_round=max_ids_per_round,
                )
                for row in result["found"]:
                    meta["context_chars"] = int(meta["context_chars"]) + len(row["content"])
                    meta["documents_in_prompt"] = int(meta["documents_in_prompt"]) + 1
                content = json.dumps(result, ensure_ascii=False)
            messages.append({"role": "tool", "tool_call_id": tid, "content": content})

    return AGENTIC_NOT_FOUND, meta


async def run_agentic_router_phase(
    *,
    client: Any,
    model_name: str,
    base_messages: List[Dict[str, Any]],
    category: str,
    max_tokens: int,
    temperature: float,
    top_p: float,
    max_rounds: int = 3,
    max_ids_per_round: int = 3,
    max_total_ids: int | None = None,
) -> Tuple[Dict[str, str], Dict[str, Any]]:
    """Tool-only retrieval: merge full document bodies by id (order = first seen)."""
    store = get_store()
    cap = max_total_ids if max_total_ids is not None else settings.AGENTIC_RAG_ROUTER_MAX_TOTAL_IDS
    meta: Dict[str, Any] = {
        "mode": "agentic_rag_router",
        "category": category,
        "tool_rounds": 0,
        "context_chars": 0,
        "documents_in_prompt": 0,
        "retrieved_ids": [],
    }
    messages = list(base_messages)
    retrieved: Dict[str, str] = {}

    for round_i in range(max_rounds):
        payload = {
            "model": model_name,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
            "tools": [REQUEST_DOCUMENTS_TOOL],
            "tool_choice": "auto",
        }
        resp = await _post_chat_completions_with_retries(client, payload)
        data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            meta["note"] = "vllm_empty_choices"
            break
        choice = choices[0]
        msg = choice.get("message") or {}
        tool_calls = msg.get("tool_calls") or []

        if not tool_calls:
            meta["tool_rounds"] = round_i
            break

        meta["tool_rounds"] = round_i + 1
        messages.append(
            {"role": "assistant", "content": msg.get("content"), "tool_calls": tool_calls}
        )

        remaining = max(0, cap - len(retrieved))
        per_round_cap = max(0, min(max_ids_per_round, remaining))

        for tc in tool_calls:
            tid = tc.get("id") or f"call_{round_i}"
            fn = tc.get("function") or {}
            name = fn.get("name") or ""
            args = _parse_tool_args(fn.get("arguments"))
            if name != "request_documents":
                content = json.dumps({"error": f"unknown_tool:{name}"}, ensure_ascii=False)
            else:
                ids = args.get("ids") or []
                if not isinstance(ids, list):
                    ids = [str(ids)]
                if per_round_cap <= 0:
                    result: Dict[str, Any] = {"found": [], "not_found": [str(x) for x in ids]}
                else:
                    result = _request_documents(
                        store,
                        category,
                        [str(x) for x in ids],
                        max_ids_per_round=per_round_cap,
                    )
                for row in result.get("found") or []:
                    doc_id = row.get("id") or ""
                    body = row.get("content") or ""
                    if doc_id and doc_id not in retrieved:
                        retrieved[doc_id] = body
                        if len(retrieved) >= cap:
                            break
                meta["context_chars"] = sum(len(t) for t in retrieved.values())
                meta["documents_in_prompt"] = len(retrieved)
                content = json.dumps(result, ensure_ascii=False)
            messages.append({"role": "tool", "tool_call_id": tid, "content": content})

        if len(retrieved) >= cap:
            meta["tool_rounds"] = round_i + 1
            break

    meta["retrieved_ids"] = list(retrieved.keys())
    meta["context_chars"] = sum(len(t) for t in retrieved.values())
    meta["documents_in_prompt"] = len(retrieved)
    return retrieved, meta


async def run_agentic_answer_phase(
    *,
    client: Any,
    model_name: str,
    messages: List[Dict[str, Any]],
    max_tokens: int,
    temperature: float,
    top_p: float,
) -> Tuple[str, Dict[str, Any]]:
    """Single chat completion without tools (normal RAG answer turn)."""
    meta: Dict[str, Any] = {"mode": "agentic_rag_answer", "tool_rounds": 0}
    payload = {
        "model": model_name,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "top_p": top_p,
    }
    resp = await _post_chat_completions_with_retries(client, payload)
    data = resp.json()
    choices = data.get("choices") or []
    if not choices:
        return "⚠️ Réponse vide du serveur d'inférence.", {**meta, "note": "vllm_empty_choices"}
    msg = (choices[0].get("message") or {})
    text = (msg.get("content") or "").strip()
    if not text:
        return AGENTIC_NOT_FOUND, meta
    return text, meta
