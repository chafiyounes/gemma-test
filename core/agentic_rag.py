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

from core.documents import DOCS_DIR, DOCS_MD_DIR, DOCS_TXT_DIR, DocStore, get_store

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
1) Read the document catalog below (each row has id, path, section_1).
2) Pick the most relevant IDs from section_1 descriptions.
3) Call request_documents with 1-3 IDs.
4) If retrieved docs are insufficient, call request_documents again with different IDs.
5) Max 3 tool rounds total. If still insufficient, answer exactly with:
   "{not_found}"
6) Final answer must be in the same language style as the user.
7) Never expose internal tool details or catalog internals to the user.

Document catalog (JSON):
{catalog_json}
""".strip()


@dataclass
class MapEntry:
    id: str
    path: str
    section_1: str

    def to_dict(self) -> Dict[str, str]:
        return {"id": self.id, "path": self.path, "section_1": self.section_1}


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
    candidates = [
        DOCS_MD_DIR / category / f"{stem}.md",
        DOCS_TXT_DIR / category / f"{stem}.txt",
        DOCS_DIR / category / f"{stem}.docx",
    ]
    for p in candidates:
        if p.is_file():
            try:
                return str(p.relative_to(Path(__file__).resolve().parent.parent))
            except Exception:
                return str(p)
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
                section_1=_extract_section_1(d.text),
            )
        )
    return rows


def make_agentic_system_prompt(catalog: List[MapEntry]) -> str:
    catalog_json = json.dumps([r.to_dict() for r in catalog], ensure_ascii=False, indent=2)
    return AGENTIC_SYSTEM_PROMPT_TEMPLATE.format(
        not_found=AGENTIC_NOT_FOUND,
        catalog_json=catalog_json,
    )


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
