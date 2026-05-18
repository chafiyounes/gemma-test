"""Input gating, multilingual fallbacks, and RAG query helpers."""
from __future__ import annotations

import re
import unicodedata
from typing import List

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
    r"kifash|kifach|daba|wakha|safi|zwin|bzaf|walo|lm3n|khasso|khass|kat|"
    r"katsal|kaysa2al|sa2al|ngoulo|khotowat|khottowat|ner3awad|n7aydo|mo3yana|"
    r"usta3mel|t9riqa|katlab|bghay|mherres|3lamlni|lamlni|telobhom|"
    r"ntelobhom|ntebi3|ntebi3ohom|y9der|dair|bach|"
    r"lqaha|kan9drach"
    r")\b",
    re.IGNORECASE,
)

_FRENCH_HINTS = re.compile(
    r"\b("
    r"le|la|les|un|une|des|du|de|et|ou|mon|ma|mes|son|sa|ses|leur|nos|vos|"
    r"vous|nous|comment|pourquoi|quelle|quel|quels|quelles|est-ce|"
    r"c'est|qu'est|d'où|où|dont|chez|avec|sans|pour|dans|sur|être|êtes|"
    r"statut|colis|livraison|client|vendeur|adresse|facture|remboursement|"
    r"plateforme|procédure|merci|bonjour|bonne|jours|cordialement"
    r")\b",
    re.IGNORECASE,
)

_ENGLISH_HINTS = re.compile(
    r"\b(the|what|how|why|when|vendor|delivery|customer|region|process|please)\b",
    re.IGNORECASE,
)

# Spanish/Portuguese/Italian-looking Latin that is NOT a serviced language.
# IMPORTANT: do **not** use bare ``que`` / ``esta`` — they false-positive French.
_NON_SERVICE_LATIN_HINTS = re.compile(
    r"(?:"
    r"[¿¡]|"
    r"\bqué\b|"
    r"\b(?:por\s+qué|porque)\b|"
    r"\bcóm[oa]\b|"
    r"\bdónde\b|"
    r"\bcuándo\b|"
    r"\busted(?:es)?\b|"
    r"\b(?:señor|señora|señorit[ao])\b|"
    r"\bgracias\b|"
    r"\bpor\s+favor\b|"
    r"\bhola\b|"
    r"\b(?:nosotros|nosotras|vosotros|vosotras)\b|"
    r"\b(?:está|están|estás|esté|estén)\b|"
    r"\b\w*ñ\w*"
    r")",
    re.IGNORECASE,
)


def answer_language_instruction_suffix(bucket: str) -> str:
    """Short suffix appended to the last user message so the model matches answer language.

    The main SYSTEM_PROMPT is French-heavy; models often drift to French without this nudge.
    """
    b = (bucket or "fr").lower()
    if b == "darija":
        return (
            "\n\n[Consigne langue] Réponds **entièrement en darija marocaine** (même registre que la question). "
            "Pas d’intro ni d’explication en français administratif."
        )
    if b == "ar":
        return "\n\n[Language] أجب بالكامل بالعربية وفق أسلوب السؤال (فصحى أو دارجة)."
    if b == "en":
        return "\n\n[Language] Answer **entirely in English**, matching the user’s question."
    if b == "es":
        return "\n\n[Language] Réponds en **français** (langue de service du guichet)."
    return "\n\n[Consigne langue] Réponds **entièrement en français**."


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
    if _NON_SERVICE_LATIN_HINTS.search(low):
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
}
POLICY_PROFANITY["es"] = POLICY_PROFANITY["fr"]


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
    "absente des documents",
    "absente de ces documents",
    "pas dans les documents",
    "pas dans les procédures",
    "n'est pas dans les documents",
    "ne figure pas dans les documents",
    "l'information que tu demandes est absente",
    "l'information demandée est absente",
    "information est absente",
)


def claims_absent_in_docs_response(model_text: str) -> bool:
    """True if the model claims the answer is not in the (supposedly provided) procedures."""
    low = (model_text or "").lower()
    if any(m in low for m in _NOT_FOUND_MARKERS):
        return True
    if "absent" in low and "document" in low:
        return True
    if "introuvable" in low and ("procédure" in low or "document" in low):
        return True
    return False


def unsupported_latin_language_message(text: str) -> str | None:
    """If Latin text looks like a non-serviced language (e.g. Spanish), return **French** notice."""
    if re.search(r"[\u0600-\u06FF]", text or ""):
        return None
    if not (text or "").strip():
        return None
    low = _nfkc_lower(text or "")
    if not _NON_SERVICE_LATIN_HINTS.search(low):
        return None
    return POLICY_UNSUPPORTED_LANG["fr"]


def normalize_not_found_response(
    user_message: str, model_text: str, *, rag_context_chars: int = 0
) -> str:
    """If the model used the old single-language fallback, map to user language.

    When substantial RAG text was injected, do **not** collapse answers to the short
    NOT_FOUND templates — that hides recoverable procedure content.
    """
    if rag_context_chars >= 400:
        return model_text
    low = (model_text or "").lower()
    if not any(m in low for m in _NOT_FOUND_MARKERS):
        return model_text
    b = detect_lang_bucket(user_message)
    if b in ("es",):
        b = "en"
    return NOT_FOUND.get(b, NOT_FOUND["fr"])
