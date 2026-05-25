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
            "Pas d’intro ni d’explication en français administratif. "
            "Si la question est en **latin (arabizi)**, réponds **en latin** aussi ; n’impose pas l’arabe en caractères arabes sauf si l’utilisateur en a déjà mis."
        )
    if b == "ar":
        return "\n\n[Language] أجب بالكامل بالعربية وفق أسلوب السؤال (فصحى أو دارجة)."
    if b == "en":
        return "\n\n[Language] Answer **entirely in English**, matching the user’s question."
    if b == "es":
        return "\n\n[Language] Réponds en **français** (langue de service du guichet)."
    return "\n\n[Consigne langue] Réponds **entièrement en français**."


def continuation_followup_message(bucket: str) -> str:
    """User turn when the model stopped with finish_reason=length (mid-answer truncation)."""
    b = (bucket or "fr").lower()
    if b == "en":
        return (
            "Continue your previous answer **exactly** where you stopped—same language, "
            "same step numbering. Do not repeat the introduction."
        )
    if b == "ar":
        return (
            "أكمل إجابتك **بالضبط** من حيث توقفت؛ نفس اللغة ونفس تعداد الخطوات. "
            "لا تعُد المقدمة."
        )
    if b == "darija":
        return (
            "كمّل الجواب **من اللي وقفتي** بنفس اللغة وبنفس الأرقام ديال الخطوات. "
            "ما تعاودش المقدمة من الأول."
        )
    return (
        "Poursuis ta réponse **exactement** là où tu t'es arrêté : même langue, même "
        "numérotation d'étapes. Ne répète pas l'introduction."
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


POLICY_GREETING: dict[str, str] = {
    "fr": "Bonjour ! Comment puis-je vous aider sur les procédures SENDIT ?",
    "en": "Hello! How can I help you with SENDIT procedures?",
    "ar": "مرحبًا! كيف يمكنني مساعدتك في إجراءات SENDIT؟",
    "darija": "Salam! Kifach n9der n3awnk f procedures dyal SENDIT?",
}


POLICY_HELP: dict[str, str] = {
    "fr": (
        "Je suis l’assistant SENDIT pour les **procédures internes** (colis, livraison, "
        "vendeur, retour, remboursement, etc.). Posez votre question sur un cas concret."
    ),
    "en": (
        "I am the SENDIT assistant for **internal procedures** (parcels, delivery, "
        "vendor, returns, refunds, etc.). Ask a concrete question about your case."
    ),
    "ar": (
        "أنا مساعد SENDIT لل**إجراءات الداخلية** (الطرود، التسليم، البائع، الإرجاع، "
        "الاسترداد، إلخ). اطرح سؤالك عن حالة محددة."
    ),
    "darija": (
        "Ana assistant dyal SENDIT l **procedures internes** (colis, livraison, vendeur, "
        "retour, remboursement…). Sa2al 3la cas concret dyalek."
    ),
}


POLICY_OFF_TOPIC: dict[str, str] = {
    "fr": (
        "Je ne traite que les **procédures SENDIT** (logistique, livraison, colis, "
        "support client interne). Merci de poser une question liée à SENDIT."
    ),
    "en": (
        "I only handle **SENDIT procedures** (logistics, delivery, parcels, internal "
        "customer support). Please ask a question related to SENDIT."
    ),
    "ar": (
        "أتعامل فقط مع **إجراءات SENDIT** (اللوجستيات، التسليم، الطرود، دعم العملاء "
        "الداخلي). يُرجى طرح سؤال متعلق بـ SENDIT."
    ),
    "darija": (
        "Kan traiti ghir **procedures SENDIT** (logistique, livraison, colis, support "
        "client interne). Sa2al chi haja m3a SENDIT."
    ),
}


POLICY_THANKS: dict[str, str] = {
    "fr": "Avec plaisir. N’hésitez pas si vous avez une autre question sur les procédures SENDIT.",
    "en": "You're welcome. Feel free to ask if you have another question about SENDIT procedures.",
    "ar": "على الرحب والسعة. لا تتردد إذا كان لديك سؤال آخر حول إجراءات SENDIT.",
    "darija": "Marhba. Ma t7tajch tssal 3la chi so2al akhor 3la procedures SENDIT.",
}


_GREETING_EXACT = frozenset(
    _nfkc_lower(w)
    for w in (
        "hi", "hello", "hey", "yo", "hola", "bonjour", "salut", "coucou", "bonsoir",
        "good morning", "good evening", "good afternoon", "hello there",
        "salam", "slm", "labas", "kif dayr", "kifach dayr", "kif dayra",
        "مرحبا", "السلام عليكم", "سلام", "أهلا", "اهلا",
    )
)

_HELP_ONLY = re.compile(
    r"^\s*(?:"
    r"can you help(?: me)?|could you help(?: me)?|help me(?: please)?|"
    r"peux[- ]?tu m['’]?aider|pouvez[- ]?vous m['’]?aider|"
    r"pourriez[- ]?vous m['’]?aider|"
    r"besoin d['’]?aide|j['’]?ai besoin d['’]?aide|"
    r"how can you help(?: me)?|what can you help(?: me)? with|"
    r"i need help|need help|"
    r"tu peux m['’]?aider|vous pouvez m['’]?aider|"
    r"عندك مساعدة|تقدر تساعدني|واش تقدر تساعدني"
    r")\s*[.!?…]*\s*$",
    re.IGNORECASE,
)

_META_ONLY = re.compile(
    r"^\s*(?:"
    r"what can you do|who are you|what do you do|what are you|"
    r"comment [çc]a marche|c['’]est quoi|tu fais quoi|"
    r"what is this|how does this work"
    r")\s*[.!?…]*\s*$",
    re.IGNORECASE,
)

_THANKS_ONLY = re.compile(
    r"^\s*(?:"
    r"merci(?: beaucoup)?|thank you|thanks(?: a lot)?|thx|ty|"
    r"شكرا|شكرًا|متشكر|baraka llah fik|choukran|chokran"
    r")\s*[.!?…]*\s*$",
    re.IGNORECASE,
)

_SENDIT_DOMAIN = re.compile(
    r"\b("
    r"sendit|colis|livraison|livrer|ramassage|expédition|expedition|exped|"
    r"vendeur|vendor|client|tracking|retour|remboursement|litige|"
    r"adresse|facture|stock|procédure|procedure|sop|injoignable|"
    r"tournée|tournee|pickup|warehouse|entrepôt|entrepot|"
    r"coordonn|téléphone|telephone|numéro|numero|gsm|portable|"
    r"plateforme|dashboard|boutique|expéditeur|expediteur|"
    r"statut|envoi|distribu|livreur|koli|livrez|ramas"
    r")\b",
    re.IGNORECASE,
)

_OFF_TOPIC_MARKERS = re.compile(
    r"\b("
    r"weather|météo|meteo|forecast|"
    r"capital of|world cup|football|soccer|basketball|"
    r"recipe|cook(?:ing)?|pasta|pizza|"
    r"joke|blague|funny story|"
    r"movie|film|music|song|album|"
    r"president|election|politic|"
    r"bitcoin|crypto|stock market|"
    r"restaurant|hotel|vacation|holiday|travel|visa|"
    r"homework|math problem|physics|"
    r"who won|who is the|tell me about the history of"
    r")\b",
    re.IGNORECASE,
)

_QUESTIONISH = re.compile(
    r"(?:\?|\b(?:comment|pourquoi|quand|où|ou|quel|quelle|quels|quelles|"
    r"what|how|why|when|where|which|who|can i|do i|is there|are there|"
    r"ash|wach|chno|chnowa|kifach|3lach|fin)\b)",
    re.IGNORECASE,
)


def _intent_bucket(user_message: str) -> str:
    b = detect_lang_bucket(user_message)
    if b == "es":
        return "en"
    return b if b in POLICY_GREETING else "fr"


def _strip_for_intent(text: str) -> str:
    t = _nfkc_lower(text or "")
    t = re.sub(r"[^\w\s\u0600-\u06FF']+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def has_sendit_domain_markers(text: str) -> bool:
    return bool(_SENDIT_DOMAIN.search(text or ""))


def classify_conversation_intent(message: str) -> str | None:
    """Return greeting/help/thanks/off_topic, or None for a procedure-style query."""
    raw = (message or "").strip()
    if not raw:
        return None
    if is_continuation_message(raw):
        return None
    norm = _strip_for_intent(raw)
    if not norm:
        return None
    if norm in _GREETING_EXACT or (len(norm) <= 18 and norm.split()[0] in _GREETING_EXACT):
        return "greeting"
    if _THANKS_ONLY.match(raw):
        return "thanks"
    if _HELP_ONLY.match(raw) or _META_ONLY.match(raw):
        return "help_request"
    if has_sendit_domain_markers(raw):
        return None
    if _OFF_TOPIC_MARKERS.search(raw):
        return "off_topic"
    if _QUESTIONISH.search(raw) and len(norm.split()) >= 3:
        return "off_topic"
    return None


def conversation_preflight_response(message: str) -> tuple[str, str] | None:
    """Fixed reply before RAG/LLM when the turn is not a procedure question."""
    intent = classify_conversation_intent(message)
    if not intent:
        return None
    bucket = _intent_bucket(message)
    if intent == "greeting":
        return intent, POLICY_GREETING.get(bucket, POLICY_GREETING["fr"])
    if intent == "help_request":
        return intent, POLICY_HELP.get(bucket, POLICY_HELP["fr"])
    if intent == "thanks":
        return intent, POLICY_THANKS.get(bucket, POLICY_THANKS["fr"])
    if intent == "off_topic":
        return intent, POLICY_OFF_TOPIC.get(bucket, POLICY_OFF_TOPIC["fr"])
    return None


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
    """True if the model claims the answer is not in the (supposedly provided) procedures.

    Uses word boundaries for French *absent/absente* so we do not match arbitrary substrings,
    and requires procedure/document context for absence-style claims (reduces false positives).
    """
    low = (model_text or "").lower()
    if any(m in low for m in _NOT_FOUND_MARKERS):
        return True
    has_proc_or_doc = (
        "document" in low
        or "documents" in low
        or "procédure" in low
        or "procedure" in low
        or "procedures" in low
    )
    if has_proc_or_doc and (
        re.search(r"\babsents?\b", low)
        or re.search(r"\babsente\b", low)
        or re.search(r"\babsence\b", low)
    ):
        return True
    if "introuvable" in low and ("procédure" in low or "document" in low or "documents" in low):
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
