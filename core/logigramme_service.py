"""Admin logigramme generation and persistence (procedures only)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx

from app_config.settings import settings
from core.documents import DocStore, get_store
from core.logigramme_llm import (
    MAX_DOC_CHARS,
    generate_logigramme,
    load_procedure_text,
    strip_code_fence,
    validate_mermaid,
)
from core.logigrammes_store import (
    PROCEDURES_CATEGORY,
    LogigrammeStoreError,
    delete,
    read,
    save,
)

REFINE_SYSTEM = (
    "Tu génères uniquement du code Mermaid flowchart TD valide en français, "
    "organisé en subgraphs swimlanes par acteur SENDIT (Magasinier, Système Sendit, "
    "Chauffeur, Stock, Service Qualité, etc.) — uniquement les acteurs présents dans la procédure."
)


class LogigrammeServiceError(Exception):
    pass


def _assert_procedures(category: str) -> None:
    if (category or "").strip() != PROCEDURES_CATEGORY:
        raise LogigrammeServiceError(
            f"logigrammes are only supported for category {PROCEDURES_CATEGORY!r}"
        )


def get_status(*, category: str, stem: str) -> dict:
    _assert_procedures(category)
    st = (stem or "").strip()
    if not st:
        raise LogigrammeServiceError("stem is required")
    mermaid = read(category, st)
    return {"exists": mermaid is not None, "mermaid": mermaid or ""}


def save_logigramme(*, category: str, stem: str, mermaid: str) -> dict:
    _assert_procedures(category)
    st = (stem or "").strip()
    if not st:
        raise LogigrammeServiceError("stem is required")
    try:
        path = save(category, st, mermaid)
    except LogigrammeStoreError as exc:
        raise LogigrammeServiceError(str(exc)) from exc
    return {"ok": True, "path": str(path)}


def remove_logigramme(*, category: str, stem: str) -> dict:
    _assert_procedures(category)
    st = (stem or "").strip()
    if not st:
        raise LogigrammeServiceError("stem is required")
    deleted = delete(category, st)
    return {"ok": True, "deleted": deleted}


def generate_mermaid(
    *,
    category: str,
    stem: str,
    messages: Optional[List[Dict[str, str]]] = None,
    current_mermaid: str = "",
    store: Optional[DocStore] = None,
    model: Optional[str] = None,
) -> dict:
    _assert_procedures(category)
    st = (stem or "").strip()
    if not st:
        raise LogigrammeServiceError("stem is required")

    doc_store = store or get_store()
    try:
        procedure_text = load_procedure_text(doc_store, category, st)
    except ValueError as exc:
        raise LogigrammeServiceError(str(exc)) from exc

    base_url = settings.VLLM_BASE_URL.rstrip("/")
    mdl = model or settings.VLLM_MODEL_NAME

    with httpx.Client(base_url=base_url, timeout=120.0) as client:
        user_messages = [m for m in (messages or []) if (m.get("content") or "").strip()]
        if not user_messages and not (current_mermaid or "").strip():
            outcome = generate_logigramme(
                document_text=procedure_text,
                fmt="mermaid",
                client=client,
                model=mdl,
            )
            return {
                "mermaid": outcome.cleaned,
                "syntax_valid": outcome.syntax_valid,
                "retried": outcome.retried,
                "latency_ms": outcome.latency_ms,
                "error": outcome.error,
            }

        draft = strip_code_fence((current_mermaid or "").strip())
        if not draft and user_messages:
            outcome = generate_logigramme(
                document_text=procedure_text,
                fmt="mermaid",
                client=client,
                model=mdl,
            )
            draft = outcome.cleaned

        history_lines: List[str] = []
        for msg in user_messages:
            role = (msg.get("role") or "user").strip()
            content = (msg.get("content") or "").strip()
            if content:
                history_lines.append(f"{role}: {content}")

        refine_prompt = (
            "Voici la procédure SENDIT source:\n\n"
            f"{procedure_text[:MAX_DOC_CHARS]}\n\n"
        )
        if draft:
            refine_prompt += (
                "Logigramme Mermaid actuel:\n```\n"
                f"{draft}\n```\n\n"
            )
        if history_lines:
            refine_prompt += "Demandes de l'utilisateur:\n" + "\n".join(history_lines) + "\n\n"
        refine_prompt += (
            "Produis UNIQUEMENT le logigramme Mermaid `flowchart TD` révisé, "
            "organisé en subgraphs par acteur SENDIT (un subgraph par rôle impliqué dans la procédure). "
            "Labels avec <br/> si besoin. Fidèle à la procédure, en français. Pas de markdown fence."
        )

        payload: Dict[str, Any] = {
            "model": mdl,
            "messages": [
                {"role": "system", "content": REFINE_SYSTEM},
                {"role": "user", "content": refine_prompt},
            ],
            "max_tokens": 2048,
            "temperature": 0.25,
        }
        r = client.post("/v1/chat/completions", json=payload, timeout=120.0)
        r.raise_for_status()
        data = r.json()
        msg = data["choices"][0].get("message") or {}
        raw = (msg.get("content") or "").strip()
        cleaned = strip_code_fence(raw)
        syntax_valid = validate_mermaid(cleaned)
        return {
            "mermaid": cleaned,
            "syntax_valid": syntax_valid,
            "retried": False,
            "latency_ms": 0,
            "error": "" if syntax_valid else "invalid mermaid output",
        }
