"""Grounded deduction rules: combine document passages with labeled inferences."""
from __future__ import annotations

import re
from typing import List, Optional

from app_config.settings import settings

DEDUCTION_SYSTEM_SECTION = """
## Raisonnement fondé sur les documents (déductions autorisées)
- Tu peux **combiner** plusieurs passages des **DOCUMENTS DE RÉFÉRENCE** et en **déduire** une conclusion **uniquement** si chaque maillon est explicitement écrit dans ces extraits (pas de connaissance générale SENDIT hors documents).
- **Étiquetage obligatoire** pour toute conclusion non copiée mot pour mot : une ligne **Déduction :** … puis **Fondé sur :** [noms exacts des documents / sections citées].
- Les faits **énoncés par l'utilisateur** ou listés dans **MÉMOIRE DU FIL** peuvent servir de prémisses ; ne les traite pas comme preuve documentaire sauf s'ils sont aussi dans les extraits.
- **Interdit** : délais, tarifs, statuts, règles internes, contacts ou processus **non** présents dans les documents — même si cela semble « logique ».
- Questions **composées** : décompose en sous-points ; réponds à chaque sous-point avec procédure directe ou déduction étiquetée ; indique clairement ce qui reste sans base documentaire (une phrase courte).
- Si le fil mélange **banalités** (salutations, remerciements) et une question SENDIT, ignore le bruit et réponds à la partie métier.
""".strip()


_DEDUCTION_LINE_RE = re.compile(
    r"(?:^|\n)\s*(?:\*\*)?d[ée]duction\s*:?\s*(?:\*\*)?\s*(.+?)(?=\n\s*(?:\*\*)?(?:fond[ée]\s+sur|source)\s*:|\n\n|\Z)",
    re.IGNORECASE | re.DOTALL,
)
_GROUNDED_ON_RE = re.compile(
    r"(?:\*\*)?fond[ée]\s+sur\s*:?\s*(?:\*\*)?\s*(.+?)(?=\n\n|\n\s*\*\*|\Z)",
    re.IGNORECASE | re.DOTALL,
)


def deduction_policy_enabled() -> bool:
    return bool(settings.GROUNDED_DEDUCTION_ENABLED)


def compose_system_prompt_with_deduction(base_prompt: str) -> str:
    if not deduction_policy_enabled():
        return base_prompt
    marker = "## Documents fournis"
    if marker in base_prompt:
        head, tail = base_prompt.split(marker, 1)
        return f"{head.rstrip()}\n\n{DEDUCTION_SYSTEM_SECTION}\n\n{marker}{tail}"
    return f"{base_prompt.rstrip()}\n\n{DEDUCTION_SYSTEM_SECTION}"


def extract_labeled_deductions(answer: str) -> List[dict]:
    """Parse **Déduction :** / **Fondé sur :** pairs from model output."""
    text = (answer or "").strip()
    if not text:
        return []
    out: List[dict] = []
    for m in _DEDUCTION_LINE_RE.finditer(text):
        conclusion = re.sub(r"\s+", " ", m.group(1)).strip(" -*")
        if len(conclusion) < 8:
            continue
        tail = text[m.end() : m.end() + 400]
        src_m = _GROUNDED_ON_RE.search(tail)
        sources = ""
        if src_m:
            sources = re.sub(r"\s+", " ", src_m.group(1)).strip(" -*")
        out.append({"conclusion": conclusion[:500], "sources": sources[:300]})
    return out


def format_thread_memory_block(memory: Optional["ThreadMemory"]) -> str:
    from core.thread_memory import ThreadMemory  # noqa: PLC0415 — avoid cycle at import

    if not memory or memory.is_empty():
        return ""
    return memory.to_prompt_block()


def compose_system_prompt_with_thread_memory(base_prompt: str, memory: Optional["ThreadMemory"]) -> str:
    block = format_thread_memory_block(memory)
    if not block:
        return base_prompt
    marker = "## Priorité"
    if marker in base_prompt:
        head, tail = base_prompt.split(marker, 1)
        return f"{head.rstrip()}\n\n{block}\n\n{marker}{tail}"
    return f"{base_prompt.rstrip()}\n\n{block}"
