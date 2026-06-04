"""Answer-language detection, system prompt blocks, and post-generation compliance."""
from __future__ import annotations

import re
from typing import Literal

AnswerLang = Literal["en", "fr", "darija", "ar", "es"]

LANGUAGE_BLOCK: dict[str, str] = {
    "en": """
## OUTPUT LANGUAGE (mandatory — overrides examples below)
- The user's question is in **ENGLISH**. Your **entire** reply MUST be in English (intro, steps, conclusion).
- Your **first sentence** must be in English. Do **not** open with "D'après", "Voici", "Il est", "Selon".
- **DOCUMENTS DE RÉFÉRENCE** may be in French: translate procedure content into English in your answer.
- You may keep SENDIT product labels as in the docs (e.g. Annulé, Refusé, Liste des colis).
""".strip(),
    "fr": """
## LANGUE DE SORTIE (obligatoire — prime sur les exemples ci-dessous)
- La question est en **FRANÇAIS**. Réponse **entièrement en français** (intro, étapes, conclusion).
- **Première phrase en français** — pas d'introduction en anglais.
- Les **DOCUMENTS DE RÉFÉRENCE** peuvent être en français : reformule fidèlement en français.
""".strip(),
    "darija": """
## LANGUE DE SORTIE (obligatoire)
- La question est en **darija marocaine** (latin / arabizi). Réponse **entièrement en darija** du début à la fin.
- Pas d'intro ni d'explication en français administratif ("D'abord…", "Il faut…", "Voici…").
- Si la question est en **latin**, réponds en **latin** ; n'impose pas l'arabe en caractères sauf si l'utilisateur l'a utilisé.
- Les **DOCUMENTS DE RÉFÉRENCE** peuvent être en français : traduis le fond en darija naturelle.
- Tu peux garder les termes métier usuels : colis, livraison, vendeur, SENDIT, statuts produit.
""".strip(),
    "ar": """
## لغة الإخراج (إلزامي)
- السؤال بالعربية. أجب **بالكامل** بالعربية (فصحى أو دارجة حسب أسلوب السؤال).
- لا تبدأ بجملة فرنسية أو إنجليزية.
""".strip(),
    "es": """
## LANGUE DE SORTIE (obligatoire)
- Langue de service du guichet : réponds en **français** (la question n'est pas dans une langue prise en charge).
""".strip(),
}

_FRENCH_OPENING_RE = re.compile(
    r"^\s*(?:d['']?après|voici|il est|selon|pour|dans ce cas|ce statut|le statut|"
    r"il convient|afin de|concernant|l['']?assistant)",
    re.IGNORECASE,
)

_ENGLISH_OPENING_RE = re.compile(
    r"^\s*(?:according to|based on|here are|the status|you can|to verify|"
    r"it is important|if the client|for the vendor|in this case)",
    re.IGNORECASE,
)

_DARIJA_OPENING_RE = re.compile(
    r"^\s*(?:bach|wakha|khass|khassek|daba|awalan|lwl|fham|chno|ila kan)",
    re.IGNORECASE,
)


def compose_system_prompt_with_language(base_prompt: str, bucket: str) -> str:
    """Insert mandatory language block immediately after the role header."""
    b = (bucket or "fr").lower()
    if b not in LANGUAGE_BLOCK:
        b = "fr"
    block = LANGUAGE_BLOCK[b]
    marker = "## Priorité"
    if marker in base_prompt:
        head, tail = base_prompt.split(marker, 1)
        return f"{head.rstrip()}\n\n{block}\n\n{marker}{tail}"
    return f"{base_prompt.rstrip()}\n\n{block}"


def detect_response_language(text: str) -> str:
    """Best-effort language of model output (opening + sample)."""
    sample = (text or "").strip()[:500]
    if not sample:
        return "unknown"
    if re.search(r"[\u0600-\u06FF]", sample):
        from core.chat_policy import _DARIJA_HINTS  # noqa: PLC0415

        if _DARIJA_HINTS.search(sample) and not re.search(
            r"(الذي|التي|بحسب|وفقا)", sample
        ):
            return "darija"
        return "ar"
    low = sample.lower()
    if _FRENCH_OPENING_RE.search(sample):
        return "fr"
    if _ENGLISH_OPENING_RE.search(sample):
        return "en"
    if _DARIJA_OPENING_RE.search(low):
        return "darija"
    try:
        from langdetect import detect  # noqa: PLC0415

        code = detect(sample)
        if code == "en":
            return "en"
        if code == "fr":
            return "fr"
    except Exception:
        pass
    return "unknown"


def response_matches_bucket(text: str, bucket: str) -> bool:
    """False when the opening clearly contradicts the required answer language."""
    b = (bucket or "fr").lower()
    if b == "es":
        b = "fr"
    detected = detect_response_language(text)
    if detected == "unknown":
        return True
    if b == "darija":
        if detected == "fr" and _FRENCH_OPENING_RE.search((text or "").strip()[:280]):
            return False
        return detected in ("darija", "ar")
    if b == "en":
        return detected == "en"
    if b == "fr":
        return detected in ("fr", "unknown")
    if b == "ar":
        return detected in ("ar", "darija")
    return detected == b


def language_repair_followup_content(expected_bucket: str, user_question: str) -> str:
    """User turn for one rewrite when output language mismatched."""
    labels = {
        "en": "English",
        "fr": "French",
        "darija": "Moroccan Darija (same script as the user's question)",
        "ar": "Arabic",
    }
    b = (expected_bucket or "fr").lower()
    if b == "es":
        b = "fr"
    label = labels.get(b, "French")
    q = (user_question or "").strip()
    if len(q) > 650:
        q = q[:650] + "…"
    return (
        f"Your previous answer was **not** in {label}. "
        f"Rewrite the **same** answer entirely in {label}.\n\n"
        f"Keep the same facts, steps, and **Source:** line(s). "
        f"Do not add new scenarios.\n\n"
        f"**User question:**\n{q}"
    )
