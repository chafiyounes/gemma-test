import logging
from typing import Optional

import httpx

from app_config.settings import settings
from core.chat_policy import (
    POLICY_PROFANITY,
    POLICY_UNSUPPORTED_LANG,
    detect_lang_bucket,
    has_unsupported_script,
    message_contains_profanity,
    normalize_not_found_response,
    retrieval_anchor_query,
    unsupported_latin_language_message,
)
from core.documents import get_store

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Tu es l'assistant IA officiel de SENDIT, une entreprise marocaine de logistique et de livraison.
Ton rôle est de répondre avec une PRÉCISION ABSOLUE aux questions des collaborateurs concernant les procédures internes (SOP).

CONTEXTE FOURNI :
Ci-dessous, tu recevras des extraits pertinents des documents de référence (récupération BM25). Chaque extrait commence par "### Document : [Nom]".

INSTRUCTIONS CRITIQUES :
1. EXACTITUDE : Ta réponse doit s'appuyer **UNIQUEMENT** sur les documents fournis. Ne fais aucune supposition et n'ajoute aucune information externe.
2. CITATION : Si tu trouves la réponse, tu **DOIS OBLIGATOIREMENT** citer le nom exact du document source à la fin de ta réponse (ex: "Source : [Nom du document]").
3. HORS SUJET / INTROUVABLE : Si la réponse ne se trouve dans AUCUN des documents fournis, réponds en **une courte phrase dans la même langue que l'utilisateur** (français, anglais, arabe standard MSA, ou darija). Sans inventer. Ne change pas de langue.
4. FORMAT : Sois clair, direct et structuré. Utilise des listes à puces pour les règles, ou des étapes numérotées pour les procédures. Ne fais pas d'introductions inutiles.
5. EXHAUSTIVITÉ : Si la question porte sur une liste (ex: produits interdits), fournis la liste complète telle qu'elle apparaît dans le document de référence.
6. SUITE / CONTINUE : Si l'utilisateur demande de poursuivre (ex. « continue », « suite », « كمل »), reprends **exactement** là où ton dernier message s'est arrêté — sans repartir de zéro — en t'appuyant sur les mêmes documents et sur l'historique de conversation.

LANGUES ET STYLE :
- Réponds par défaut en **Français** (langue des procédures).
- Si l'utilisateur pose la question en **Anglais**, réponds en Anglais.
- Si l'utilisateur pose la question en **Darija marocaine** (en caractères arabes ou en Arabizi comme "kifash", "ch7al"), réponds de manière claire et professionnelle dans la même langue. Tu peux garder les termes métier **en français** (remboursement, vendeur, système) quand la traduction approximative nuirait à la clarté.
"""


class GemmaModel:
    """Client for the vLLM OpenAI-compatible inference server running Gemma."""

    def __init__(self):
        self.available: bool = False
        self._base_url = settings.VLLM_BASE_URL.rstrip("/")
        self._model_name = settings.VLLM_MODEL_NAME
        self._api_key = settings.VLLM_API_KEY or "no-key"
        self._client: Optional[httpx.AsyncClient] = None

        try:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=httpx.Timeout(timeout=settings.VLLM_TIMEOUT),
                headers={"Authorization": f"Bearer {self._api_key}"},
            )
            self.available = True
            logger.info(
                "GemmaModel client ready → %s  model=%s",
                self._base_url,
                self._model_name,
            )
        except Exception as exc:
            logger.error("Failed to init vLLM client: %s", exc)

    async def check_health(self) -> bool:
        if not self._client:
            return False
        try:
            resp = await self._client.get("/health", timeout=5.0)
            return resp.status_code == 200
        except Exception:
            return False

    async def generate(
        self,
        message: str,
        history: list[dict] | None = None,
        system_prompt: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        category: str | None = None,
    ) -> str:
        """Call the vLLM OpenAI-compatible chat completions endpoint."""
        if not self.available or not self._client:
            return "⚠️ LLM server is not available. Please check vLLM is running on the pod."

        hist = history or []
        bucket = detect_lang_bucket(message)

        if message_contains_profanity(message):
            return POLICY_PROFANITY.get(bucket, POLICY_PROFANITY["fr"])

        if has_unsupported_script(message):
            return POLICY_UNSUPPORTED_LANG.get(bucket, POLICY_UNSUPPORTED_LANG["fr"])

        wrong_lang = unsupported_latin_language_message(message)
        if wrong_lang:
            return wrong_lang

        sys_prompt = (system_prompt or SYSTEM_PROMPT).strip()

        try:
            ctx = None
            if category:
                store = get_store()
                corpus = store.category_corpus_chars(category)
                rq = retrieval_anchor_query(message, hist)
                if 0 < corpus <= settings.RAG_FULL_CATEGORY_MAX_CHARS:
                    ctx = store.build_all_docs_context(
                        category=category,
                        max_chars=settings.RAG_INJECT_MAX_CHARS,
                    )
                    logger.info(
                        "RAG full category inject: %d corpus chars → %d ctx chars",
                        corpus,
                        len(ctx or ""),
                    )
                else:
                    ctx = store.build_context(
                        rq,
                        category=category,
                        k=settings.RAG_BM25_K,
                        max_chars=settings.RAG_INJECT_MAX_CHARS,
                    )
            if ctx:
                cat_hint = f" (catégorie : {category})" if category else ""
                sys_prompt = (
                    sys_prompt
                    + f"\n\n--- DOCUMENTS DE RÉFÉRENCE{cat_hint} ---\n"
                    + ctx
                    + "\n--- FIN DES DOCUMENTS ---"
                )
        except Exception as exc:
            logger.warning("Doc retrieval failed: %s", exc)

        messages = [{"role": "system", "content": sys_prompt}]

        for turn in hist:
            role = turn.get("role", "user")
            content = turn.get("content", "")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})

        messages.append({"role": "user", "content": message})

        payload = {
            "model": self._model_name,
            "messages": messages,
            "max_tokens": max_tokens or settings.MAX_NEW_TOKENS,
            "temperature": temperature or settings.TEMPERATURE,
            "top_p": settings.TOP_P,
        }

        try:
            resp = await self._client.post("/v1/chat/completions", json=payload)
            resp.raise_for_status()
            data = resp.json()
            raw = data["choices"][0]["message"]["content"].strip()
            return normalize_not_found_response(message, raw)
        except httpx.HTTPStatusError as exc:
            logger.error("vLLM HTTP error %s: %s", exc.response.status_code, exc.response.text)
            return f"⚠️ Model error ({exc.response.status_code}). Please try again."
        except Exception as exc:
            logger.error("vLLM request failed: %s", exc)
            return "⚠️ Failed to reach the model server. Please check connectivity."

    async def aclose(self) -> None:
        if self._client:
            await self._client.aclose()
