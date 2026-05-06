import asyncio
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

# After deploy / start_all, vLLM often needs several minutes before :8002 accepts HTTP.
_VLLM_CONNECT_RETRIES = 4
_VLLM_CONNECT_RETRY_DELAY_S = 15.0


def _vllm_unavailable_message(base_url: str, bucket: str, *, after_retries: bool) -> str:
    """User-facing text when vLLM cannot be reached (loading vs broken host)."""
    wait_hint = (
        "Réessayez dans une minute ou deux. "
        if after_retries
        else ""
    )
    if bucket == "en":
        return (
            "⚠️ The inference server is not accepting connections yet "
            f"({base_url}). After a restart, loading Gemma can take **several minutes** "
            "before this port opens. "
            + wait_hint
            + f"On the pod, `curl -sS {base_url}/v1/models` should return JSON when ready. "
            "If it never does, check `tmux attach -t gemma-test`, GPU memory, or recycle the pod."
        )
    if bucket == "ar":
        return (
            "⚠️ خادم الاستدلال (vLLM) غير متاح بعد على المنفذ 8002. "
            "بعد إعادة التشغيل قد يستغرق تحميل النموذج **عدة دقائق** قبل فتح المنفذ. "
            + (wait_hint.replace("Réessayez", "أعد المحاولة") if wait_hint else "")
            + "على الـ pod نفّذ: `curl -sS "
            + base_url
            + "/v1/models` — يجب أن يعيد JSON عند الجاهزية."
        )
    # fr, darija, es → French message (service language for ops)
    return (
        "⚠️ Le moteur vLLM ne répond pas encore sur "
        f"{base_url}. Après un `start_all.sh` ou un déploiement, le chargement des "
        "poids peut prendre **plusieurs minutes** : le port 8002 ne s’ouvre qu’une fois "
        "le modèle prêt. "
        + wait_hint
        + f"Sur le pod : `curl -sS {base_url}/v1/models` doit renvoyer du JSON quand c’est bon. "
        "Si ça échoue toujours : `tmux attach -t gemma-test` (voir le panneau vllm), "
        "ou recycler le pod (mémoire GPU bloquée)."
    )

# System prompt: keep ONE place for behaviour (language, RAG, continuations).
# Retrieval: French/Darija queries may get French synonym expansion for BM25;
# English queries stay English-only (see core/documents.py).
SYSTEM_PROMPT = """
## Rôle
Tu es l’assistant IA interne de **SENDIT** (logistique / livraison, Maroc). Tu aides les collaborateurs sur les **procédures officielles (SOP)** décrites dans les documents fournis.

## Documents fournis (contexte RAG)
- Après ce bloc, tu reçois une section **DOCUMENTS DE RÉFÉRENCE** : extraits ou dossier complet d’une catégorie (ex. `procedures`).
- Chaque morceau commence par `### Document : [Nom]`.
- **Ancrage factuel** : n’invente pas de faits qui ne figurent pas dans ces documents. Tu peux **ordonner, reformuler et regrouper** ce qui y est écrit.

## Procédures voisines et reformulation métier (important)
- Les questions (surtout en **darija / mélange FR**) utilisent souvent des mots différents des SOP (ex. « modifier numéro », « colis f livraison »). **Traduis mentalement** vers les notions des procédures : coordonnées, contact, client, colis, statut, livraison, expédition, ramassage, retour, litige, etc.
- Si **aucun passage** ne répond mot pour mot mais que le contexte décrit une situation **du même domaine** (ex. mise à jour de **téléphone / adresse**, colis **en cours de livraison** vs en préparation, **injoignable**, litige), **applique** les règles et étapes **les plus proches** en les reliant clairement à la question : étapes numérotées, limites éventuelles (« les documents précisent surtout le cas X ; pour une livraison déjà engagée, cela implique… ») uniquement si c’est **déductible** des textes fournis.
- Réserver la phrase type **« information absente des documents »** au cas où le contexte **ne traite vraiment aucun angle utile** du sujet (pas uniquement parce qu’une formulation exacte manque).

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
- **Uniquement** si aucun extrait ne permet de répondre **même partiellement** au thème (après avoir cherché une procédure voisine, voir ci-dessus).
- Une **seule phrase courte**, dans la **même langue** que la question.
- Ne dis pas que tu as cherché sur Internet.

## Suite / « continue »
- Si l’utilisateur demande de poursuivre (« continue », « suite », « كمل », etc.), reprends **exactement** là où ton message assistant **précédent** s’est arrêté, sans recommencer depuis zéro, en restant aligné sur les mêmes documents et l’historique.

## Limites
- Pas de conseil juridique/médical général hors procédures.
- Si un message est **totalement hors** logistique SENDIT **et** aucun document ne s’y rattache, applique la règle « information absente ».
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
                    expand_hints = bucket in ("fr", "darija", "en")
                    ctx = store.build_all_docs_context(
                        category=category,
                        max_chars=settings.RAG_INJECT_MAX_CHARS,
                        query=rq,
                        expand_for_retrieval=expand_hints,
                    )
                    logger.info(
                        "RAG full category inject: %d corpus chars → %d ctx chars",
                        corpus,
                        len(ctx or ""),
                    )
                else:
                    # BM25: FR/darija hints + EN→FR lemmas when English keywords match
                    # (French SOPs still match "vendor", "delivery", "phone", …).
                    expand_hints = bucket in ("fr", "darija", "en")
                    ctx = store.build_context(
                        rq,
                        category=category,
                        k=settings.RAG_BM25_K,
                        max_chars=settings.RAG_INJECT_MAX_CHARS,
                        expand_fr_darija_hints=expand_hints,
                    )
                    if not ctx:
                        ctx = store.build_all_docs_context(
                            category=category,
                            max_chars=settings.RAG_INJECT_MAX_CHARS,
                            query=rq,
                            expand_for_retrieval=expand_hints,
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
            resp = None
            for attempt in range(_VLLM_CONNECT_RETRIES):
                try:
                    resp = await self._client.post("/v1/chat/completions", json=payload)
                    resp.raise_for_status()
                    break
                except httpx.ConnectError:
                    if attempt + 1 < _VLLM_CONNECT_RETRIES:
                        logger.warning(
                            "vLLM unreachable (attempt %s/%s), retry in %ss",
                            attempt + 1,
                            _VLLM_CONNECT_RETRIES,
                            _VLLM_CONNECT_RETRY_DELAY_S,
                        )
                        await asyncio.sleep(_VLLM_CONNECT_RETRY_DELAY_S)
                    else:
                        return _vllm_unavailable_message(
                            self._base_url, bucket, after_retries=True
                        )
            if resp is None:
                return _vllm_unavailable_message(self._base_url, bucket, after_retries=True)
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
        except httpx.ConnectError:
            return _vllm_unavailable_message(self._base_url, bucket, after_retries=False)
        except Exception as exc:
            logger.error("vLLM request failed: %s", exc, exc_info=True)
            return (
                "⚠️ Unexpected error calling the inference server. "
                f"If the stack was just restarted, wait for vLLM: `{self._base_url}/v1/models`."
            )

    async def aclose(self) -> None:
        if self._client:
            await self._client.aclose()
