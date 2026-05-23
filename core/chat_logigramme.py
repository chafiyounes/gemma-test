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
    "à la situation. Ne décris pas le Mermaid en prose (« le diagramme est intégré… »). "
    "Le diagramme publié s'affiche automatiquement quand il est dans les documents. "
    "Si tu dois montrer une version adaptée, place le code UNIQUEMENT dans un bloc:\n"
    "```logigramme\nflowchart TD\n...\n```\n"
    "Sans autre texte dans ce bloc.]"
)

LOGIGRAMME_SYSTEM_SECTION = """
## Logigrammes (diagrammes de flux)
- Ne remplace jamais un logigramme par une description textuelle du flux quand l'utilisateur en demande un.
- Si le Mermaid figure dans **DOCUMENTS DE RÉFÉRENCE** (section `## Logigramme (flowchart)` ou bloc ` ```mermaid `), réponds par les **étapes numérotées** adaptées ; le chat affiche le diagramme séparément.
- Pour une **variante adaptée** à la situation, ajoute un bloc dédié (seul contenu du bloc) :
```logigramme
flowchart TD
...
```
- N'écris pas de code Mermaid hors de ce bloc `logigramme`.
""".strip()

LOGIGRAMME_AGENTIC_TOOL_HINT = (
    "When the user asks for a logigramme / flowchart / diagramme de flux, call "
    "`request_logigramme` with the same catalog **id**(s) as the procedure "
    "(e.g. `procedures/Proc-produits_interdits` or the plain stem when the catalog uses stems only). "
    "Load the procedure with `request_documents` first if needed."
)

LOGIGRAMME_RESPONSE_FENCE_RE = re.compile(
    r"```(?:logigramme|mermaid)\s*\n([\s\S]*?)```",
    re.IGNORECASE,
)

MERMAID_IN_CONTEXT_RE = re.compile(
    r"```mermaid\s*\n([\s\S]*?)\n```",
    re.IGNORECASE,
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


def extract_logigramme_fences(text: str) -> tuple[str, list[str]]:
    """Strip ```logigramme / ```mermaid fences from assistant text for display."""
    codes: list[str] = []

    def repl(match: re.Match[str]) -> str:
        code = (match.group(1) or "").strip()
        if code:
            codes.append(code)
        return ""

    stripped = LOGIGRAMME_RESPONSE_FENCE_RE.sub(repl, text or "")
    stripped = re.sub(r"\n{3,}", "\n\n", stripped).strip()
    return stripped, codes


def procedure_stem_from_rag(rag_meta: dict) -> Optional[str]:
    stem = primary_procedure_stem(rag_meta)
    if stem:
        return stem
    for doc_id in (rag_meta or {}).get("retrieved_ids") or []:
        raw = str(doc_id or "").strip()
        if not raw:
            continue
        if "/" in raw:
            cat, st = raw.split("/", 1)
            if cat.strip() == PROCEDURES_CATEGORY and st.strip():
                return st.strip()
        else:
            return raw
    for row in (rag_meta or {}).get("logigrammes_fetched") or []:
        st = (row.get("stem") or row.get("id") or "").strip()
        if st:
            if "/" in st:
                cat, rest = st.split("/", 1)
                if cat.strip() == PROCEDURES_CATEGORY:
                    return rest.strip()
            return st
    return None


def mermaid_from_context(rag_meta: dict) -> Optional[Dict[str, str]]:
    ctx = (rag_meta or {}).get("context_full") or (rag_meta or {}).get("context_preview") or ""
    if not ctx.strip():
        return None
    for match in MERMAID_IN_CONTEXT_RE.finditer(ctx):
        cleaned = normalize_mermaid(match.group(1))
        if validate_mermaid(cleaned):
            return {
                "mermaid": cleaned,
                "stem": procedure_stem_from_rag(rag_meta) or "",
                "source": "context",
            }
    return None


def inline_logigramme_payload(codes: list[str], rag_meta: dict) -> Optional[Dict[str, str]]:
    for raw in reversed(codes or []):
        cleaned = normalize_mermaid(raw)
        if validate_mermaid(cleaned):
            return {
                "mermaid": cleaned,
                "stem": procedure_stem_from_rag(rag_meta) or "",
                "source": "inline",
            }
    return None


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


def should_attach_logigramme(message: str, rag_meta: dict) -> bool:
    meta = rag_meta or {}
    if wants_logigramme(message):
        return True
    if meta.get("logigramme_tool_used"):
        return True
    if meta.get("logigrammes_fetched"):
        return True
    return False


def logigramme_from_fetched(rag_meta: dict) -> Optional[Dict[str, str]]:
    for row in (rag_meta or {}).get("logigrammes_fetched") or []:
        cleaned = normalize_mermaid((row.get("mermaid") or "").strip())
        if validate_mermaid(cleaned):
            return {
                "mermaid": cleaned,
                "stem": (row.get("stem") or row.get("id") or "").strip(),
                "source": "fetched",
            }
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
    fetched = logigramme_from_fetched(meta)
    if fetched:
        return fetched

    from_context = mermaid_from_context(meta)
    if from_context:
        return from_context

    stem = procedure_stem_from_rag(meta)
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
    """Mutate rag_meta with logigramme when user asked or agent fetched Mermaid."""
    if not should_attach_logigramme(message, rag_meta):
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


def process_chat_logigramme(
    *,
    message: str,
    step_answer: str,
    rag_meta: Dict[str, Any],
    store: Optional[DocStore] = None,
    model: Optional[str] = None,
) -> tuple[str, Dict[str, Any]]:
    """Strip inline fences, attach diagram metadata, return display text + rag_meta."""
    meta = dict(rag_meta or {})
    display_text, inline_codes = extract_logigramme_fences(step_answer)

    inline_payload = inline_logigramme_payload(inline_codes, meta)
    if inline_payload:
        meta["logigramme"] = inline_payload
        return display_text, meta

    meta = attach_logigramme_if_requested(
        message=message,
        step_answer=display_text,
        rag_meta=meta,
        store=store,
        model=model,
    )
    return display_text, meta
