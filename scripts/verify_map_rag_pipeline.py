#!/usr/bin/env python3
"""Offline verification for map catalog + retrieval used by two-phase agentic RAG.

Checks (no vLLM):
- BM25 ranks the expected fixture doc for a French/English-style query.
- Catalog rows include id, path, objective, section_1.
- PDF-relative stems resolve to a plausible data/documents/... path hint.

Optional live check: set USE_VLLM=1 and ensure VLLM_BASE_URL + vLLM are up; the script will
run one router completion (tool calling must be enabled on the server).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _check_bm25_cat_a() -> None:
    from core.documents import get_store

    store = get_store()
    if "cat_a" not in store.indexes:
        raise SystemExit("SKIP: no cat_a in DocStore (missing data/documents_txt/cat_a?)")
    hits = store.retrieve("multi_sub fixture category", category="cat_a", k=3)
    if not hits or hits[0].name != "file_a":
        top = hits[0].name if hits else "(no hits)"
        raise SystemExit(
            f"BM25 expected file_a first for cat_a query, got {top!r}. "
            f"Docs: {[d.name for d in store.indexes['cat_a'].docs]}"
        )


def _check_catalog_shape() -> None:
    from core.agentic_rag import build_document_catalog
    from core.documents import get_store

    store = get_store()
    if "cat_a" not in store.indexes:
        raise SystemExit("SKIP: no cat_a for catalog shape check")
    rows = build_document_catalog(store, "cat_a")
    if not rows:
        raise SystemExit("catalog empty for cat_a")
    raw = rows[0].to_dict()
    for key in ("id", "path", "objective", "section_1"):
        if key not in raw:
            raise SystemExit(f"catalog row missing {key!r}: {raw!r}")


def _check_resolve_pdf_stem() -> None:
    from core.agentic_rag import _resolve_doc_path

    p = _resolve_doc_path("procedures", "pdf/Demande de remboursement - colis endommagé")
    if "procedures" not in p or "pdf" not in p:
        raise SystemExit(f"unexpected resolve for pdf stem: {p!r}")


async def _maybe_vllm_router_smoke() -> None:
    if os.environ.get("USE_VLLM", "").strip().lower() not in ("1", "true", "yes"):
        return
    import httpx

    from app_config.settings import settings
    from core.agentic_rag import (
        REQUEST_DOCUMENTS_TOOL,
        _parse_tool_args,
        _post_chat_completions_with_retries,
        build_document_catalog,
        make_router_system_prompt,
    )
    from core.documents import get_store

    store = get_store()
    cat = "cat_a"
    if cat not in store.indexes:
        print("SKIP vLLM: no cat_a corpus")
        return
    catalog = build_document_catalog(store, cat)
    system = make_router_system_prompt(catalog)
    messages = [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": "Which document explains multi_sub fixture category naming?",
        },
    ]
    payload = {
        "model": settings.VLLM_MODEL_NAME,
        "messages": messages,
        "max_tokens": 256,
        "temperature": settings.AGENTIC_RAG_TEMPERATURE,
        "tools": [REQUEST_DOCUMENTS_TOOL],
        "tool_choice": "auto",
    }
    base = settings.VLLM_BASE_URL.rstrip("/")
    headers = {}
    if settings.VLLM_API_KEY:
        headers["Authorization"] = f"Bearer {settings.VLLM_API_KEY}"
    async with httpx.AsyncClient(
        base_url=base,
        timeout=httpx.Timeout(120.0),
        headers=headers or None,
    ) as client:
        resp = await _post_chat_completions_with_retries(client, payload)
    data = resp.json()
    msg = (data.get("choices") or [{}])[0].get("message") or {}
    tcs = msg.get("tool_calls") or []
    if not tcs:
        raise SystemExit(f"vLLM smoke: expected tool_calls, got message={msg!r}")
    fn = (tcs[0].get("function") or {})
    if fn.get("name") != "request_documents":
        raise SystemExit(f"vLLM smoke: expected request_documents, got {fn!r}")
    args = _parse_tool_args(fn.get("arguments"))
    ids = args.get("ids") or []
    print("vLLM router smoke OK: tool args =", json.dumps(ids, ensure_ascii=False))


def main() -> None:
    _check_bm25_cat_a()
    _check_catalog_shape()
    _check_resolve_pdf_stem()
    print("Offline map+RAG pipeline checks: OK")
    asyncio.run(_maybe_vllm_router_smoke())


if __name__ == "__main__":
    main()
