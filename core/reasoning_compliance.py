"""Case-brief prompt injection and post-generation reasoning repair."""
from __future__ import annotations

import re
from typing import Optional

from core.case_brief import CaseBrief

_ASSERTIVE_CUES_RE = re.compile(
    r"(?:"
    r"est marqué|a refusé|a annulé|a annule|n['']a pas pu|n’a pas pu|"
    r"parce que le client|lorsque le client|le client annule|le client a|"
    r"because the client|when the client|the client cancel|"
    r"c['']est parce que|cela signifie que|cela peut se faire"
    r")",
    re.IGNORECASE,
)


def format_case_brief_block(brief: CaseBrief) -> str:
    facts = "\n".join(f"- {f}" for f in brief.stated_facts) or "- (aucun fait explicite listé)"
    avoid = (
        "\n".join(f"- {x}" for x in brief.do_not_assume)
        or "- (ne pas inventer de causes ou acteurs non mentionnés)"
    )
    return (
        "## CAS UTILISATEUR (obligatoire — prime sur les exemples ci-dessous)\n"
        f"- **Objectif :** {brief.user_goal}\n"
        f"- **Faits énoncés :**\n{facts}\n"
        f"- **Ne pas supposer (ne pas traiter comme vrai) :**\n{avoid}\n"
        "- Réponds **d'abord** à l'objectif ci-dessus.\n"
        "- Si les **DOCUMENTS DE RÉFÉRENCE** décrivent un **autre** cas, donne les étapes sous forme "
        "conditionnelle (« seulement si … ») au lieu d'affirmer que c'est la situation actuelle.\n"
        "- **Une branche principale** par réponse ; branches secondaires uniquement en « si / sinon » "
        "liées à une information manquante."
    ).strip()


def compose_system_prompt_with_case_brief(
    base_prompt: str, brief: Optional[CaseBrief]
) -> str:
    """Insert case brief block before ## Priorité (after language block if present)."""
    if not brief:
        return base_prompt
    block = format_case_brief_block(brief)
    marker = "## Priorité"
    if marker in base_prompt:
        head, tail = base_prompt.split(marker, 1)
        return f"{head.rstrip()}\n\n{block}\n\n{marker}{tail}"
    return f"{base_prompt.rstrip()}\n\n{block}"


def _significant_tokens(phrase: str) -> list[str]:
    return [
        t
        for t in re.findall(r"[\wàâéèêëïîôùûç'-]+", (phrase or "").lower())
        if len(t) >= 4
    ]


def violates_case_brief(answer: str, brief: CaseBrief) -> bool:
    """True when the answer assertively states something listed in do_not_assume."""
    low = (answer or "").lower()
    if not low or not brief.do_not_assume:
        return False
    if not _ASSERTIVE_CUES_RE.search(low):
        return False
    for item in brief.do_not_assume:
        tokens = _significant_tokens(item)
        if not tokens:
            continue
        matched = sum(1 for t in tokens if t in low)
        if matched >= min(2, len(tokens)):
            return True
        if len(tokens) == 1 and tokens[0] in low:
            return True
    return False


def reasoning_repair_followup_content(brief: CaseBrief, user_question: str) -> str:
    q = (user_question or "").strip()
    if len(q) > 650:
        q = q[:650] + "…"
    avoid = "; ".join(brief.do_not_assume[:6]) or "(see case brief)"
    facts = "; ".join(brief.stated_facts[:6]) or brief.user_goal
    return (
        "Your previous answer **assumed facts the user did not state** or described the wrong scenario.\n\n"
        f"**User goal:** {brief.user_goal}\n"
        f"**Stated facts only:** {facts}\n"
        f"**Do NOT assert as true:** {avoid}\n\n"
        "Rewrite using **DOCUMENTS DE RÉFÉRENCE** only. Use conditional wording "
        "(« seulement si … ») for branches that may not apply. "
        "Do not add new actors or causes.\n\n"
        f"**User question:**\n{q}"
    )
