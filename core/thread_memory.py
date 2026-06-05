"""Per-thread memory: user-stated facts and document-grounded deductions across turns."""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from app_config.settings import settings
from core.case_brief import CaseBrief
from core.deduction_policy import extract_labeled_deductions

logger = logging.getLogger(__name__)


@dataclass
class ThreadMemory:
    stated_facts: List[str] = field(default_factory=list)
    derived_facts: List[dict] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not self.stated_facts and not self.derived_facts

    def to_metadata(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_metadata(cls, data: Any) -> "ThreadMemory":
        if not isinstance(data, dict):
            return cls()
        stated = data.get("stated_facts")
        derived = data.get("derived_facts")
        if not isinstance(stated, list):
            stated = []
        if not isinstance(derived, list):
            derived = []
        clean_stated = [str(x).strip() for x in stated if str(x).strip()]
        clean_derived: List[dict] = []
        for item in derived:
            if not isinstance(item, dict):
                continue
            concl = str(item.get("conclusion") or "").strip()
            if not concl:
                continue
            clean_derived.append(
                {
                    "conclusion": concl[:500],
                    "sources": str(item.get("sources") or "").strip()[:300],
                }
            )
        return cls(stated_facts=clean_stated[:20], derived_facts=clean_derived[:20])

    def to_prompt_block(self) -> str:
        if self.is_empty():
            return ""
        lines = [
            "## MÉMOIRE DU FIL (faits établis — réutiliser ; ne pas contredire sans preuve documentaire)",
        ]
        if self.stated_facts:
            lines.append("### Faits énoncés par l'utilisateur (cette conversation)")
            for f in self.stated_facts[-12:]:
                lines.append(f"- {f}")
        if self.derived_facts:
            lines.append("### Déductions fondées (issues des documents, fil précédent)")
            for d in self.derived_facts[-10:]:
                src = (d.get("sources") or "").strip()
                concl = (d.get("conclusion") or "").strip()
                if src:
                    lines.append(f"- {concl} — **Fondé sur :** {src}")
                else:
                    lines.append(f"- {concl}")
        lines.append(
            "- Tu peux t'appuyer sur ces éléments pour les **suites** du fil ; "
            "toute **nouvelle** déduction doit rester ancrée dans les DOCUMENTS DE RÉFÉRENCE actuels."
        )
        return "\n".join(lines)

    def merge_turn(
        self,
        *,
        brief: Optional[CaseBrief],
        answer: str,
        user_message: str,
    ) -> "ThreadMemory":
        """Return updated memory after one chat turn (does not mutate self)."""
        stated = list(self.stated_facts)
        derived = list(self.derived_facts)

        if brief and brief.stated_facts:
            for fact in brief.stated_facts:
                f = fact.strip()
                if f and f not in stated:
                    stated.append(f)

        for item in extract_labeled_deductions(answer):
            concl = item.get("conclusion", "")
            if not concl:
                continue
            if any(d.get("conclusion") == concl for d in derived):
                continue
            derived.append(item)

        cap_s = max(4, int(settings.THREAD_MEMORY_MAX_STATED_FACTS))
        cap_d = max(4, int(settings.THREAD_MEMORY_MAX_DERIVED_FACTS))
        return ThreadMemory(
            stated_facts=stated[-cap_s:],
            derived_facts=derived[-cap_d:],
        )


def thread_memory_enabled() -> bool:
    return bool(settings.THREAD_MEMORY_ENABLED)


def retrieval_query_with_memory(
    message: str,
    history: List[dict] | None,
    brief: Optional[CaseBrief],
    memory: Optional[ThreadMemory],
) -> str:
    """Extend retrieval query with thread memory keywords."""
    from core.chat_policy import retrieval_anchor_query  # noqa: PLC0415

    base = retrieval_anchor_query(message, history)
    if brief and brief.retrieval_query_fr:
        base = f"{brief.retrieval_query_fr} {base}".strip()
    if not memory or memory.is_empty():
        return base
    extras: List[str] = []
    for f in memory.stated_facts[-3:]:
        extras.append(f[:120])
    for d in memory.derived_facts[-2:]:
        extras.append(str(d.get("conclusion", ""))[:120])
    if extras:
        return f"{base} {' '.join(extras)}".strip()[:500]
    return base


def serialize_memory(memory: Optional[ThreadMemory]) -> str:
    if not memory:
        return "{}"
    return json.dumps(memory.to_metadata(), ensure_ascii=False)


def deserialize_memory(raw: Optional[str]) -> ThreadMemory:
    if not raw:
        return ThreadMemory()
    try:
        return ThreadMemory.from_metadata(json.loads(raw))
    except (json.JSONDecodeError, TypeError):
        logger.warning("thread_memory: invalid JSON, resetting")
        return ThreadMemory()
