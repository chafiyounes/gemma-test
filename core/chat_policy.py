"""Input gating, multilingual fallbacks, and RAG query helpers."""
from __future__ import annotations

import re
import unicodedata
from typing import List, Mapping

# Short follow-ups that carry no topical tokens for BM25 — anchor on prior user turn.
_CONTINUATION_ONLY = re.compile(
    r"^\s*(continue|continuer|suite|more|next|go on|carry on|further|\.{2,}|…|"
    r"و\s*كمل|كمل|أكمل|اكمل|عاود|زيد|برك\s*من\s*هنا|كمّل)\s*[.!?…]*\s*$",
    re.IGNORECASE,
)


def is_continuation_message(message: str) -> bool:
    m = (message or "").strip()
    if not m:
        return False
    if _CONTINUATION_ONLY.match(m):
        return True
    if len(m) <= 18 and m.lower() in {"continue", "suite", "more", "next"}:
        return True
    return False


def retrieval_anchor_query(message: str, history: List[dict] | None) -> str:
    """BM25 needs real terms. Re-use last substantive user question for 'continue'-style turns."""
    if not is_continuation_message(message):
        return message.strip()
    for turn in reversed(history or []):
        if turn.get("role") != "user":
            continue
        prev = (turn.get("content") or "").strip()
        if prev and not is_continuation_message(prev):
            return f"{prev}\n{message.strip()}"
    return message.strip()


# ── Profanity (short list; extend as needed) ──────────────────────────────
_PROFANITY = frozenset(
    w.lower()
    for w in (
        "merde", "putain", "connard", "salope", "fdp", "enculé", "ntm",
        "fuck", "shit", "bitch", "asshole", "cunt", "wtf",
        "زامل", "نيك", "كس",
    )
)


def _nfkc_lower(s: str) -> str:
    return unicodedata.normalize("NFKC", s).lower()


def message_contains_profanity(text: str) -> bool:
    t = _nfkc_lower(text)
    parts = re.split(r"[^\w\u0600-\u06FF]+", t)
    return any(p in _PROFANITY for p in parts if p)


# ── Unsupported scripts (Latin + Arabic are OK) ──────────────────────────
def has_unsupported_script(text: str) -> bool:
    for ch in text or "":
        o = ord(ch)
        if 0x0400 <= o <= 0x04FF:  # Cyrillic
            return True
        if 0x3040 <= o <= 0x30FF or 0x4E00 <= o <= 0x9FFF:  # Hiragana/Katakana / CJK
            return True
        if 0xAC00 <= o <= 0xD7AF:  # Hangul
            return True
    return False


_DARIJA_HINTS = re.compile(
    r"\b("
    r"chno|chnowa|ash|wash|wach|bgh|bgha|bghit|bghiti|dyal|dial|diali|3lach|3lash|"
    r"kifash|kifach|daba|wakha|safi|zwin|bzaf|walo|lm3n|khasso|khass|kat"
    r")\b",
    re.IGNORECASE,
)

_FRENCH_HINTS = re.compile(
    r"\b(le|la|les|un|une|des|vous|nous|comment|pourquoi|procédure|quelle|"
    r"merci|bonjour|êtes|êtes-vous)\b",
    re.IGNORECASE,
)

_ENGLISH_HINTS = re.compile(
    r"\b(the|what|how|why|when|vendor|delivery|customer|region|process|please)\b",
    re.IGNORECASE,
)

_SPANISH_HINTS = re.compile(
    r"\b(que\s|qué|porque|usted|señor|señora|gracias|por favor|esta\s|esto\s)\b",
    re.IGNORECASE,
)


def detect_lang_bucket(text: str) -> str:
    """Bucket for templated replies: 'fr' | 'en' | 'ar' | 'darija' | 'es'."""
    t = text or ""
    if re.search(r"[\u0600-\u06FF]", t):
        if _DARIJA_HINTS.search(t) and not re.search(
            r"(الذي|التي|بحسب|وفقا|يُذكر|وفقًا)", t
        ):
            return "darija"
        return "ar"
    low = t.lower()
    if _SPANISH_HINTS.search(low):
        return "es"
    if _DARIJA_HINTS.search(low):
        return "darija"
    en_n = len(_ENGLISH_HINTS.findall(low))
    fr_n = len(_FRENCH_HINTS.findall(low))
    if en_n > fr_n + 1:
        return "en"
    if fr_n > en_n + 1:
        return "fr"
    return "fr"


POLICY_UNSUPPORTED_LANG: dict[str, str] = {
    "fr": (
        "Ce service accepte uniquement le **français**, l'**anglais**, "
        "l'**arabe standard (MSA)** et la **darija marocaine**. "
        "Merci de reformuler dans l'une de ces langues."
    ),
    "en": (
        "This service only accepts **French**, **English**, "
        "**Modern Standard Arabic (MSA)**, and **Moroccan Darija**. "
        "Please rephrase using one of these languages."
    ),
    "ar": (
        "هذه الخدمة تقبل فقط **الفرنسية** و**الإنجليزية** و**العربية الفصحى** "
        "و**الدارجة المغربية**. يُرجى إعادة الصياغة بإحدى هذه اللغات."
    ),
    "darija": (
        "Had l'khidma كاتقبل غير **فرانساوي**, **نڭليزي**, "
        "**عربي فصيح (MSA)** و **دارجة مغربية**. عافاك عاود السؤال بوحدة من هاد اللغات."
    ),
    "es": (
        "Este servicio solo acepta **francés**, **inglés**, **árabe estándar (MSA)** "
        "y **darija marroquí**. Por favor reformule en uno de esos idiomas."
    ),
}


POLICY_PROFANITY: dict[str, str] = {
    "fr": (
        "Votre message contient un langage inapproprié. Merci de reformuler "
        "votre question de façon professionnelle. Langues acceptées : "
        "français, anglais, arabe standard (MSA) ou darija marocaine."
    ),
    "en": (
        "Your message contains inappropriate language. Please rephrase "
        "professionally. Accepted languages: French, English, Modern Standard "
        "Arabic, or Moroccan Darija."
    ),
    "ar": (
        "رسالتك تحوي ألفاظًا غير لائقة. يُرجى إعادة الصياغة باحترام. "
        "اللغات المقبولة: الفرنسية، الإنجليزية، العربية الفصحى، أو الدارجة المغربية."
    ),
    "darija": (
        "L-message dyalk فيه كلام ما مناسبش. عافاك عاود السؤال باحترام. "
        "اللغات اللي نقبلو: فرانساوي، نڭليزي، عربي فصيح، ولا دارجة مغربية."
    ),
    "es": POLICY_UNSUPPORTED_LANG["es"],
}


NOT_FOUND: dict[str, str] = {
    "fr": "Je n'ai pas trouvé cette information dans les procédures actuellement disponibles.",
    "en": "I could not find this information in the currently available procedures.",
    "ar": "لم أعثر على هذه المعلومة في الإجراءات المتاحة حاليًا.",
    "darija": (
        "Ma لقيتش هاد المعلومة فال procedures اللي عندنا دابا فالنظام."
    ),
}


_NOT_FOUND_MARKERS = (
    "je n'ai pas trouvé cette information",
    "je nai pas trouvé",
    "could not find this information",
    "pas trouvé cette information dans les procédures",
    "لم أعثر على هذه المعلومة",
    "لم اعثر على هذه المعلومة",
    "ma لقيتش",
    "ma ل9يتش",
)


def unsupported_latin_language_message(text: str) -> str | None:
    """Return policy message if Latin text looks like Spanish, else None."""
    if re.search(r"[\u0600-\u06FF]", text or ""):
        return None
    if not (text or "").strip():
        return None
    if not _SPANISH_HINTS.search(text):
        return None
    b = detect_lang_bucket(text)
    return POLICY_UNSUPPORTED_LANG.get(b, POLICY_UNSUPPORTED_LANG["fr"])


def normalize_not_found_response(user_message: str, model_text: str) -> str:
    """If the model used the old single-language fallback, map to user language."""
    low = (model_text or "").lower()
    if not any(m in low for m in _NOT_FOUND_MARKERS):
        return model_text
    b = detect_lang_bucket(user_message)
    if b in ("es",):
        b = "en"
    return NOT_FOUND.get(b, NOT_FOUND["fr"])
