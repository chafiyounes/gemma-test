"""Explicit logigramme requests in normal chat."""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional

import httpx

from app_config.settings import settings
from core.documents import DocStore, get_store
from core.logigramme_llm import MAX_DOC_CHARS, load_procedure_text
from core.logigrammes_store import PROCEDURES_CATEGORY, read
from core.mermaid_validate import normalize_mermaid, validate_mermaid

logger = logging.getLogger(__name__)

LOGIGRAMME_INTENT_RE = re.compile(
    r"\b("
    r"logigramme?s?|"
    r"diagramme\s+de\s+flux|"
    r"sch[ée]ma\s+(?:du\s+)?processus|"
    r"flowchart|"
    r"diagramme\s+(?:du\s+)?(?:processus|flux|proc[ée]dure)"
    r")\b",
    re.I,
)

DOC_HEADER_RE = re.compile(
    r"### Document : ([^\n]+?)  \(catégorie : ([^\)]+)\)",
)

LOGIGRAMME_CHAT_INSTRUCTION = (
    "\n\n[Instruction logigramme: réponds d'abord par les étapes numérotées adaptées "
    "à la situation décrite. Ne produis pas de code Mermaid dans le texte.]"
)

SITUATIONAL_SYSTEM = (
    "Tu génères uniquement du code Mermaid flowchart TD valide en français. "
    "Première ligne = flowchart TD. Subgraphs par acteur SENDIT impliqué. "
    "Le diagramme doit couvrir la situation décrite par l'utilisateur. "
    "Labels concis avec <br/> si besoin. IDs camelCase. Aucun texte hors code."
)

SITUATIONAL_USER_TEMPLATE = """Procédure source:
{procedure_text}

Situation / question de l'utilisateur:
{user_message}

Étapes déjà expliquées dans la réponse:
{step_answer}

Produis UNIQUEMENT un logigramme Mermaid flowchart TD pour CETTE situation.
Première ligne: flowchart TD.
Subgraphs par acteur. Branches de décision pertinentes pour le scénario.
Pas de markdown fence, pas de prose."""


def wants_logigramme(message: str) -> bool:
    return bool(LOGIGRAMME_INTENT_RE.search((message or "").strip()))


def augment_message_for_logigramme(message: str) -> str:
    if not wants_logigramme(message):
        return message
    return message + LOGIGRAMME_CHAT_INSTRUCTION


def primary_procedure_stem(rag_meta: dict) -> Optional[str]:
    ctx = (rag_meta or {}).get("context_full") or (rag_meta or {}).get("context_preview") or ""
    for match in DOC_HEADER_RE.finditer(ctx):
        name, cat = match.group(1).strip(), match.group(2).strip()
        if cat != PROCEDURES_CATEGORY:
            continue
        stem = name
        for ext in (".docx", ".md", ".txt"):
            if stem.lower().endswith(ext):
                stem = stem[: -len(ext)]
                break
        return stem
    return None


def _call_situational_mermaid(
    *,
    procedure_text: str,
    user_message: str,
    step_answer: str,
    model: Optional[str] = None,
) -> Optional[str]:
    body = (procedure_text or "")[:MAX_DOC_CHARS]
    if not body.strip():
        return None

    user_content = SITUATIONAL_USER_TEMPLATE.format(
        procedure_text=body,
        user_message=(user_message or "").strip()[:2000],
        step_answer=(step_answer or "").strip()[:4000],
    )
    mdl = model or settings.VLLM_MODEL_NAME
    base_url = settings.VLLM_BASE_URL.rstrip("/")

    try:
        with httpx.Client(base_url=base_url, timeout=120.0) as client:
            payload = {
                "model": mdl,
                "messages": [
                    {"role": "system", "content": SITUATIONAL_SYSTEM},
                    {"role": "user", "content": user_content},
                ],
                "max_tokens": 4096,
                "temperature": 0.25,
            }
            response = client.post("/v1/chat/completions", json=payload)
            response.raise_for_status()
            data = response.json()
            msg = data["choices"][0].get("message") or {}
            raw = (msg.get("content") or "").strip()
            cleaned = normalize_mermaid(raw)
            if validate_mermaid(cleaned):
                return cleaned
    except Exception as exc:
        logger.warning("Chat situational logigramme generation failed: %s", exc)
    return None


def resolve_logigramme_for_chat(
    *,
    user_message: str,
    step_answer: str,
    rag_meta: dict,
    store: Optional[DocStore] = None,
    model: Optional[str] = None,
) -> Optional[Dict[str, str]]:
    """Return logigramme payload for chat metadata, or None on failure."""
    meta = rag_meta or {}
    stem = primary_procedure_stem(meta)
    doc_store = store or get_store()

    if stem:
        published = read(PROCEDURES_CATEGORY, stem)
        if published:
            cleaned = normalize_mermaid(published)
            if validate_mermaid(cleaned):
                return {"mermaid": cleaned, "stem": stem, "source": "published"}

    procedure_text = ""
    if stem:
        try:
            procedure_text = load_procedure_text(doc_store, PROCEDURES_CATEGORY, stem)
        except ValueError:
            procedure_text = ""

    if not procedure_text.strip():
        procedure_text = (meta.get("context_full") or meta.get("context_preview") or "").strip()

    mermaid = _call_situational_mermaid(
        procedure_text=procedure_text,
        user_message=user_message,
        step_answer=step_answer,
        model=model,
    )
    if not mermaid:
        return None

    return {
        "mermaid": mermaid,
        "stem": stem or "",
        "source": "generated",
    }


def attach_logigramme_if_requested(
    *,
    message: str,
    step_answer: str,
    rag_meta: Dict[str, Any],
    store: Optional[DocStore] = None,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """Mutate rag_meta with logigramme block when user explicitly asked."""
    if not wants_logigramme(message):
        return rag_meta
    payload = resolve_logigramme_for_chat(
        user_message=message,
        step_answer=step_answer,
        rag_meta=rag_meta,
        store=store,
        model=model,
    )
    if payload:
        rag_meta["logigramme"] = payload
    return rag_meta
