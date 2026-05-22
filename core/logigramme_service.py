"""Admin logigramme generation and persistence (procedures only)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx

from app_config.settings import settings
from core.documents import DocStore, get_store
from core.logigramme_llm import (
    FORMAT_RETRY,
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
    read_draft,
    save,
    save_draft,
)
from core.mermaid_validate import normalize_mermaid

REFINE_SYSTEM = (
    "Tu génères uniquement du code Mermaid flowchart TD valide en français. "
    "Première ligne = flowchart TD. Subgraphs par acteur SENDIT présents dans la procédure. "
    "Le diagramme doit permettre de suivre TOUTE la procédure sans le document source. "
    "Labels détaillés: listes autorisées/interdites, restrictions, critères concrets (<br/>). "
    "Chaque décision a ses branches. IDs camelCase. Aucun texte hors code."
)

REFINE_RETRY_SUFFIX = FORMAT_RETRY["mermaid"]


class LogigrammeServiceError(Exception):
    pass


def _assert_procedures(category: str) -> None:
    if (category or "").strip() != PROCEDURES_CATEGORY:
        raise LogigrammeServiceError(
            f"logigrammes are only supported for category {PROCEDURES_CATEGORY!r}"
        )


def get_status(*, category: str, stem: str, username: str) -> dict:
    _assert_procedures(category)
    st = (stem or "").strip()
    if not st:
        raise LogigrammeServiceError("stem is required")
    user = (username or "").strip()
    if not user:
        raise LogigrammeServiceError("username is required")
    published = read(category, st)
    draft = read_draft(category, st, user)
    has_draft = draft is not None
    has_published = published is not None
    # Prefer draft in editor when present (work in progress).
    editor_mermaid = (draft or published or "") if (has_draft or has_published) else ""
    return {
        "exists": has_published,
        "published_exists": has_published,
        "mermaid": published or "",
        "draft_exists": has_draft,
        "draft_mermaid": draft or "",
        "editor_mermaid": editor_mermaid,
    }


def save_logigramme_draft(*, category: str, stem: str, mermaid: str, username: str) -> dict:
    _assert_procedures(category)
    st = (stem or "").strip()
    if not st:
        raise LogigrammeServiceError("stem is required")
    user = (username or "").strip()
    if not user:
        raise LogigrammeServiceError("username is required")
    try:
        path = save_draft(category, st, mermaid, username=user)
    except LogigrammeStoreError as exc:
        raise LogigrammeServiceError(str(exc)) from exc
    return {"ok": True, "path": str(path), "draft": True}


def save_logigramme(*, category: str, stem: str, mermaid: str, username: str) -> dict:
    _assert_procedures(category)
    st = (stem or "").strip()
    if not st:
        raise LogigrammeServiceError("stem is required")
    user = (username or "").strip()
    if not user:
        raise LogigrammeServiceError("username is required")
    try:
        path = save(category, st, mermaid, username=user)
    except LogigrammeStoreError as exc:
        raise LogigrammeServiceError(str(exc)) from exc
    return {"ok": True, "path": str(path), "published": True}


def remove_logigramme(*, category: str, stem: str) -> dict:
    _assert_procedures(category)
    st = (stem or "").strip()
    if not st:
        raise LogigrammeServiceError("stem is required")
    deleted = delete(category, st)
    return {"ok": True, "deleted": deleted}


def _refine_prompt(
    procedure_text: str,
    draft: str,
    history_lines: List[str],
) -> str:
    prompt = (
        "Voici la procédure SENDIT source:\n\n"
        f"{procedure_text[:MAX_DOC_CHARS]}\n\n"
    )
    if draft:
        prompt += f"Logigramme Mermaid actuel:\n```\n{draft}\n```\n\n"
    if history_lines:
        prompt += "Demandes de l'utilisateur:\n" + "\n".join(history_lines) + "\n\n"
    prompt += (
        "Produis UNIQUEMENT le logigramme Mermaid révisé.\n"
        "Première ligne: flowchart TD.\n"
        "Subgraphs par acteur SENDIT impliqué. IDs camelCase.\n"
        "Labels riches avec listes/critères concrets de la procédure (articles autorisés/interdits, restrictions…) via <br/>.\n"
        "Couvre toute la procédure du début à la fin, toutes les branches de décision.\n"
        "Fidèle au texte. Pas de markdown fence, pas de prose."
    )
    return prompt


def _call_refine(
    client: httpx.Client,
    *,
    model: str,
    refine_prompt: str,
    retry: bool = False,
) -> tuple[str, str]:
    user_content = refine_prompt
    if retry:
        user_content = refine_prompt + "\n\n" + REFINE_RETRY_SUFFIX
    payload: Dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": REFINE_SYSTEM},
            {"role": "user", "content": user_content},
        ],
        "max_tokens": 4096,
        "temperature": 0.25,
    }
    r = client.post("/v1/chat/completions", json=payload, timeout=120.0)
    r.raise_for_status()
    data = r.json()
    msg = data["choices"][0].get("message") or {}
    raw = (msg.get("content") or "").strip()
    cleaned = normalize_mermaid(raw)
    return raw, cleaned


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

        draft = normalize_mermaid((current_mermaid or "").strip())
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

        refine_prompt = _refine_prompt(procedure_text, draft, history_lines)
        _raw, cleaned = _call_refine(client, model=mdl, refine_prompt=refine_prompt, retry=False)
        retried = False
        if not validate_mermaid(cleaned):
            retried = True
            _raw, cleaned = _call_refine(client, model=mdl, refine_prompt=refine_prompt, retry=True)

        syntax_valid = validate_mermaid(cleaned)
        return {
            "mermaid": cleaned,
            "syntax_valid": syntax_valid,
            "retried": retried,
            "latency_ms": 0,
            "error": "" if syntax_valid else "invalid mermaid output",
        }
