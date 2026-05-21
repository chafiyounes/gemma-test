"""Generate Mermaid flowcharts (logigrammes) from procedure documents via vLLM."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional

import httpx

from app_config.settings import settings
from core.documents import DocStore, get_store

logger = logging.getLogger(__name__)

MAX_DOC_CHARS = 12_000

LOGIGRAMME_KEYWORDS = re.compile(
    r"\blogigramme\b|\bflowchart\b|\bdiagramme\b|\bdiagram\b",
    re.IGNORECASE,
)

LOGIGRAMME_PROMPT = """Tu es un expert en logigrammes SENDIT (logistique Maroc).
À partir de la procédure ci-dessous, produis UNIQUEMENT un diagramme Mermaid `flowchart TD` en français.

Règles:
- Nœuds rectangulaires pour les étapes: A[Étape]
- Nœuds losange pour les décisions: B{{Question ?}}
- Début/fin: ([Début]) ou ([Fin])
- Fidèle au texte source; n'invente pas d'étapes absentes
- Labels courts (max ~8 mots par nœud)
- Pas de markdown fence, pas d'explication, pas de commentaire Mermaid (%%, %%)

Procédure:
{document_text}
"""

LOGIGRAMME_RETRY_SUFFIX = (
    "\n\nTa réponse précédente n'était pas du Mermaid valide. "
    "Réponds UNIQUEMENT avec `flowchart TD` suivi des nœuds et flèches."
)


@dataclass
class LogigrammeResult:
    text: str
    rag: Dict[str, Any]
    document_id: str = ""


def is_logigramme_request(message: str) -> bool:
    return bool(LOGIGRAMME_KEYWORDS.search(message or ""))


def strip_mermaid_fence(raw: str) -> str:
    s = (raw or "").strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\s*", "", s)
        s = re.sub(r"\s*```\s*$", "", s)
    return s.strip()


def validate_mermaid(text: str) -> bool:
    s = strip_mermaid_fence(text)
    if not s:
        return False
    first = s.splitlines()[0].strip().lower()
    return first.startswith("flowchart") or first.startswith("graph ")


def format_logigramme_response(mermaid: str) -> str:
    body = strip_mermaid_fence(mermaid)
    return f"Voici le logigramme de la procédure :\n\n```mermaid\n{body}\n```"


def resolve_document_for_logigramme(
    store: DocStore,
    message: str,
    category: Optional[str],
) -> tuple[Optional[str], Optional[str]]:
    """Return (document_id, document_text) best matching the user message."""
    cats = store.resolve_rag_scope(category)
    if not cats:
        return None, None

    query = (message or "").strip()
    ctx = store.build_context(
        query,
        categories=cats,
        k=1,
        max_chars=MAX_DOC_CHARS,
        condense=True,
    )
    if not ctx:
        return None, None

    header_match = re.search(r"^### Document\s*:\s*(.+?)\s*(?:\(|$)", ctx, re.MULTILINE)
    if not header_match:
        return None, None

    stem = header_match.group(1).strip()
    cat = cats[0] if len(cats) == 1 else None
    if cat:
        doc_id = f"{cat}/{stem}" if "/" not in stem else stem
        text = store.get_document_by_stem(cat, stem.split("/")[-1])
    else:
        doc_id = stem
        text = store.get_document_by_catalog_id(stem, cats[0])

    if not text:
        text = re.sub(r"^### Document[^\n]*\n", "", ctx, count=1).strip()
    return doc_id, text


def generate_logigramme_mermaid(
    *,
    document_text: str,
    client: httpx.Client,
    model: Optional[str] = None,
    timeout: float = 120.0,
) -> str:
    """One vLLM call; retry once if output is not valid Mermaid."""
    body = (document_text or "")[:MAX_DOC_CHARS]
    sys_prompt = "Tu génères uniquement du code Mermaid valide (flowchart TD). Aucun texte autour."
    user_a = LOGIGRAMME_PROMPT.format(document_text=body)
    user_b = user_a + LOGIGRAMME_RETRY_SUFFIX
    mdl = model or settings.VLLM_MODEL_NAME

    def one_call(user_content: str) -> str:
        payload = {
            "model": mdl,
            "messages": [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_content},
            ],
            "max_tokens": 2048,
            "temperature": 0.25,
        }
        r = client.post("/v1/chat/completions", json=payload, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        msg = data["choices"][0].get("message") or {}
        raw = (msg.get("content") or "").strip()
        cleaned = strip_mermaid_fence(raw)
        if not validate_mermaid(cleaned):
            raise ValueError("invalid mermaid output")
        return cleaned

    try:
        return one_call(user_a)
    except Exception as first:
        logger.warning("Logigramme first pass failed: %s", first)
        return one_call(user_b)


async def generate_logigramme_mermaid_async(
    *,
    document_text: str,
    client: httpx.AsyncClient,
    model: Optional[str] = None,
    timeout: float = 120.0,
) -> str:
    body = (document_text or "")[:MAX_DOC_CHARS]
    sys_prompt = "Tu génères uniquement du code Mermaid valide (flowchart TD). Aucun texte autour."
    user_a = LOGIGRAMME_PROMPT.format(document_text=body)
    user_b = user_a + LOGIGRAMME_RETRY_SUFFIX
    mdl = model or settings.VLLM_MODEL_NAME

    async def one_call(user_content: str) -> str:
        payload = {
            "model": mdl,
            "messages": [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_content},
            ],
            "max_tokens": 2048,
            "temperature": 0.25,
        }
        r = await client.post("/v1/chat/completions", json=payload, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        msg = data["choices"][0].get("message") or {}
        raw = (msg.get("content") or "").strip()
        cleaned = strip_mermaid_fence(raw)
        if not validate_mermaid(cleaned):
            raise ValueError("invalid mermaid output")
        return cleaned

    try:
        return await one_call(user_a)
    except Exception as first:
        logger.warning("Logigramme async first pass failed: %s", first)
        return await one_call(user_b)


def generate_logigramme_for_document(
    store: DocStore,
    *,
    category: str,
    document_id: str,
    client: httpx.Client,
    model: Optional[str] = None,
) -> str:
    text = store.get_document_by_catalog_id(document_id, category)
    if not text:
        stem = document_id.split("/")[-1]
        text = store.get_document_by_stem(category, stem)
    if not text:
        raise ValueError(f"document not found: {document_id}")
    return generate_logigramme_mermaid(document_text=text, client=client, model=model)


async def answer_logigramme(
    *,
    message: str,
    category: Optional[str],
    client: httpx.AsyncClient,
    store: Optional[DocStore] = None,
) -> Optional[LogigrammeResult]:
    """Resolve a procedure and return a formatted Mermaid response, or None if not applicable."""
    if not is_logigramme_request(message):
        return None

    doc_store = store or get_store()
    doc_id, doc_text = resolve_document_for_logigramme(doc_store, message, category)
    if not doc_text:
        return LogigrammeResult(
            text="Je n'ai pas trouvé de procédure correspondante pour générer un logigramme.",
            rag={"mode": "logigramme", "note": "no_document"},
            document_id=doc_id or "",
        )

    mermaid = await generate_logigramme_mermaid_async(
        document_text=doc_text,
        client=client,
    )
    return LogigrammeResult(
        text=format_logigramme_response(mermaid),
        rag={
            "mode": "logigramme",
            "document_id": doc_id or "",
            "mermaid_lines": len(mermaid.splitlines()),
        },
        document_id=doc_id or "",
    )
