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

# System prompt: keep ONE place for behaviour (language, RAG, continuations).
# Retrieval: French/Darija queries may get French synonym expansion for BM25;
# English queries stay English-only (see core/documents.py).
SYSTEM_PROMPT = """
## Rôle
Tu es l’assistant IA interne de **SENDIT** (logistique / livraison, Maroc). Tu aides les collaborateurs sur les **procédures officielles (SOP)** décrites dans les documents fournis.

## Documents fournis (contexte RAG)
- Après ce bloc, tu reçois une section **DOCUMENTS DE RÉFÉRENCE** : extraits ou dossier complet d’une catégorie (ex. `procedures`).
- Chaque morceau commence par `### Document : [Nom]`.
- Tes réponses sur le fond doivent **strictement** s’appuyer sur ce contenu. Pas de connaissances externes, pas de suppositions.

## Langue de réponse (alignée sur l’utilisateur)
1. **Français** : si la question est en français ou par défaut quand la langue est ambiguë (les SOP sont rédigées en français).
2. **Anglais** : si la question est clairement en anglais → réponds entièrement en **anglais** (y compris citations de noms de documents si tu les cites tels quels).
3. **Arabe standard (MSA)** : si la question est en arabe classique/fusha → réponds en MSA clair et professionnel.
4. **Darija marocaine** : si la question est en darija (arabe dialectal ou arabizi) → réponds en darija **professionnelle**. Tu peux **garder les termes métier en français** (ex. remboursement, vendeur, colis, système) quand une traduction approximative ferait perdre le sens.

## Structure des réponses
- Procédures : étapes **numérotées** ou puces, ordre fidèle au document.
- **Ne t’arrête pas au milieu d’une phrase, d’un verbe ou d’une étape.** Finis l’étape en cours, puis enchaîne. Si tu distingues plusieurs cas (« Cas 1 », « Cas 2 »…), traite **chaque cas complet** (toutes les étapes de ce cas) avant de passer au suivant.
- À la fin, si tu t’appuies sur un document : une ligne **Source : [nom exact du fichier / titre du document]**.
- Si l’utilisateur demande une **liste** présente dans les docs, donne la liste **complète** telle qu’indiquée.

## Information absente des documents
- Une **seule phrase courte**, dans la **même langue** que la question.
- Ne dis pas que tu as cherché sur Internet. Ne invente rien.

## Suite / « continue »
- Si l’utilisateur demande de poursuivre (« continue », « suite », « كمل », etc.), reprends **exactement** là où ton message assistant **précédent** s’est arrêté, sans recommencer depuis zéro, en restant aligné sur les mêmes documents et l’historique.

## Limites
- Pas de conseil juridique/médical général hors procédures.
- Si un message est hors périmètre logistique SENDIT et absent des docs, applique la règle « information absente ».
""".strip()


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
                    # BM25 : synonymes FR ajoutés seulement pour questions FR/darija
                    # (les questions EN restent en mots anglais normaux).
                    expand_hints = bucket in ("fr", "darija")
                    ctx = store.build_context(
                        rq,
                        category=category,
                        k=settings.RAG_BM25_K,
                        max_chars=settings.RAG_INJECT_MAX_CHARS,
                        expand_fr_darija_hints=expand_hints,
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
            choice = data["choices"][0]
            msg = choice.get("message") or {}
            raw = (msg.get("content") or "").strip()
            finish = choice.get("finish_reason")
            usage = data.get("usage") or {}
            pt = usage.get("prompt_tokens")
            ct = usage.get("completion_tokens")
            logger.info(
                "vLLM chat done finish_reason=%s prompt_tokens=%s completion_tokens=%s max_tokens_sent=%s",
                finish,
                pt,
                ct,
                payload.get("max_tokens"),
            )
            if finish == "length":
                logger.warning(
                    "vLLM finish_reason=length (context or max_tokens hit). "
                    "Raise VLLM_MAX_MODEL_LEN / RAG_INJECT_MAX_CHARS or MAX_NEW_TOKENS. tail=%r",
                    raw[-80:] if raw else "",
                )
            return normalize_not_found_response(message, raw)
        except httpx.HTTPStatusError as exc:
            logger.error("vLLM HTTP error %s: %s", exc.response.status_code, exc.response.text)
            return f"⚠️ Model error ({exc.response.status_code}). Please try again."
        except Exception as exc:
            logger.error("vLLM request failed: %s", exc, exc_info=True)
            return (
                "⚠️ Cannot reach the inference server at "
                f"{self._base_url}. If VRAM looks busy but chat fails, vLLM may "
                "still be loading weights or nothing is listening on that URL — "
                f"wait for `curl {self._base_url}/v1/models` on the pod, then "
                "restart the API if needed. If `curl` keeps failing and "
                "`nvidia-smi` shows almost all memory used but no processes, "
                "stop and start the RunPod to clear stuck GPU memory, then run "
                "`bash start_all.sh gemma4` again."
            )

    async def aclose(self) -> None:
        if self._client:
            await self._client.aclose()
