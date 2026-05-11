import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import httpx

from app_config.settings import settings
from core.chat_policy import (
    POLICY_PROFANITY,
    POLICY_UNSUPPORTED_LANG,
    claims_absent_in_docs_response,
    detect_lang_bucket,
    has_unsupported_script,
    message_contains_profanity,
    normalize_not_found_response,
    retrieval_anchor_query,
    unsupported_latin_language_message,
)
from core.agentic_rag import build_document_catalog, make_agentic_system_prompt, run_agentic_tool_loop
from core.documents import get_store

logger = logging.getLogger(__name__)


@dataclass
class LLMGenerateResult:
    """Completion text plus RAG/debug fields for persistence and admin UI."""

    text: str
    rag: Dict[str, Any] = field(default_factory=dict)


# Second model call when the first claims "absent" despite a large RAG inject.
_RAG_REPAIR_MIN_CONTEXT_CHARS = 500
_RAG_REPAIR_TEMPERATURE = 0.35
_RAG_REPAIR_USER = (
    "Le message système contenait une section **DOCUMENTS DE RÉFÉRENCE** avec des extraits de procédures SENDIT "
    "(coordonnées / téléphone, livraison, colis, vendeur). "
    "Ta réponse précédente disait à tort que l’information n’y était pas.\n"
    "Reprends **uniquement** à partir de ces extraits : réponds **dans la même langue que la question utilisateur** "
    "(darija professionnelle si la question était en darija / mélange), avec des **étapes numérotées** pour le cas : "
    "vendeur qui veut **changer le numéro de téléphone du client** alors que le **colis est déjà en livraison**. "
    "Si les textes ne décrivent pas exactement ce cas, indique les **étapes les plus proches** (coordonnées, statut, "
    "contact livreur, etc.) et précise l’écart. "
    "Dernière ligne obligatoire : **Source :** + nom exact du document cité."
)


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
- Après ce bloc, tu peux recevoir une section **DOCUMENTS DE RÉFÉRENCE** : extraits ou dossier (parfois tronqué) d’une catégorie (ex. `procedures`).
- Chaque morceau commence par `### Document : [Nom]`.
- **Ancrage factuel** : n’invente pas de faits qui ne figurent pas dans ces documents. Tu peux **ordonner, reformuler et regrouper** ce qui y est écrit.
- **Si la section DOCUMENTS DE RÉFÉRENCE est présente et non vide** : considère que l’information pertinente s’y trouve **quelque part** (même avec une formulation différente de la question). Cherche des passages sur le **même cas métier** avant toute réponse du type « absent des documents ».

## Procédures voisines et reformulation métier (important)
- Les questions (surtout en **darija / mélange FR**) utilisent souvent des mots différents des SOP (ex. « modifier numéro », « colis f livraison »). **Traduis mentalement** vers les notions des procédures : coordonnées, contact, client, colis, statut, livraison, expédition, ramassage, retour, litige, etc.
- Si **aucun passage** ne répond mot pour mot mais que le contexte décrit une situation **du même domaine** (ex. mise à jour de **téléphone / adresse**, colis **en cours de livraison** vs en préparation, **injoignable**, litige), **applique** les règles et étapes **les plus proches** en les reliant clairement à la question : étapes numérotées, limites éventuelles (« les documents précisent surtout le cas X ; pour une livraison déjà engagée, cela implique… ») uniquement si c’est **déductible** des textes fournis.
- Réserver la phrase type **« information absente des documents »** au cas où le contexte **ne traite vraiment aucun angle utile** du sujet (pas uniquement parce qu’une formulation exacte manque).

## Langue de réponse (alignée sur l’utilisateur)
1. Toute la réponse suit la **langue dominante de la question** (intro, étapes, conclusion). Question en darija / arabizi ⇒ **darija professionnelle** ; ne pas basculer en français sauf termes métier (`colis`, `procédure`, etc.).
2. **Français** : question en français, ou ambiguë sans marqueurs darija.
3. **Anglais** : question en anglais ⇒ réponse entière en anglais.
4. **Arabe standard (MSA)** : question en fusha ⇒ MSA professionnel.
5. **Darija** : question en darija ⇒ darija + termes métier FR si utile.

## Structure des réponses
- Procédures : étapes **numérotées** ou puces, ordre fidèle au document.
- **Ne t’arrête pas au milieu d’une phrase, d’un verbe ou d’une étape.** Finis l’étape en cours, puis enchaîne. Si tu distingues plusieurs cas (« Cas 1 », « Cas 2 »…), traite **chaque cas complet** (toutes les étapes de ce cas) avant de passer au suivant.
- À la fin, si tu t’appuies sur un document : une ligne **Source : [nom exact du fichier / titre du document]**.
- Si l’utilisateur demande une **liste** présente dans les docs, donne la liste **complète** telle qu’indiquée.

## Information absente des documents
- **Uniquement** si aucun extrait ne permet de répondre **même partiellement** au thème (après avoir cherché une procédure voisine, voir ci-dessus).
- **Interdit** si la section DOCUMENTS DE RÉFÉRENCE est **non vide** : réponses du type « l’information est absente des documents », « ce n’est pas dans les procédures », ou toute formulation équivalente **sans** avoir d’abord proposé **au moins une procédure voisine** (téléphone/coordonnées **ou** colis en livraison **ou** contact livreur) avec **étapes numérotées tirées des textes** et une ligne **Source : …**. Si les textes ne couvrent vraiment aucun de ces angles, indique **explicitement** quels titres de documents tu as consultés et **quel sous-thème** manque (ex. « pas d’étape pour changement de téléphone **pendant** la tournée »).
- Une **seule phrase courte** pour le cas « vraiment absent », dans la **même langue** que la question.
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

    async def _rag_repair_turn(
        self,
        base_messages: list[dict],
        first_answer: str,
        payload_template: dict,
    ) -> str:
        """One follow-up turn when the model wrongly claims info is missing despite RAG text."""
        msgs = list(base_messages) + [
            {"role": "assistant", "content": first_answer},
            {"role": "user", "content": _RAG_REPAIR_USER},
        ]
        payload = {
            **payload_template,
            "messages": msgs,
            "temperature": _RAG_REPAIR_TEMPERATURE,
        }
        resp = await self._client.post("/v1/chat/completions", json=payload)
        resp.raise_for_status()
        data = resp.json()
        choice = data["choices"][0]
        msg = choice.get("message") or {}
        return (msg.get("content") or "").strip()

    async def generate(
        self,
        message: str,
        history: list[dict] | None = None,
        system_prompt: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        category: str | None = None,
    ) -> LLMGenerateResult:
        """Call the vLLM OpenAI-compatible chat completions endpoint."""
        rag_meta: Dict[str, Any] = {"category": category}

        if not self.available or not self._client:
            rag_meta["context_chars"] = 0
            rag_meta["note"] = "llm_client_unavailable"
            return LLMGenerateResult(
                text="⚠️ LLM server is not available. Please check vLLM is running on the pod.",
                rag=rag_meta,
            )

        hist = history or []
        bucket = detect_lang_bucket(message)

        if message_contains_profanity(message):
            return LLMGenerateResult(text=POLICY_PROFANITY.get(bucket, POLICY_PROFANITY["fr"]), rag=rag_meta)

        if has_unsupported_script(message):
            return LLMGenerateResult(
                text=POLICY_UNSUPPORTED_LANG.get(bucket, POLICY_UNSUPPORTED_LANG["fr"]),
                rag=rag_meta,
            )

        wrong_lang = unsupported_latin_language_message(message)
        if wrong_lang:
            return LLMGenerateResult(text=wrong_lang, rag=rag_meta)

        sys_prompt = (system_prompt or SYSTEM_PROMPT).strip()

        try:
            ctx = None
            if category:
                store = get_store()
                corpus = store.category_corpus_chars(category)
                rq = retrieval_anchor_query(message, hist)
                if corpus <= 0:
                    rag_meta["note"] = "category_empty_or_missing"
                elif 0 < corpus <= settings.RAG_FULL_CATEGORY_MAX_CHARS:
                    expand_hints = bucket in ("fr", "darija", "en")
                    ctx = store.build_all_docs_context(
                        category=category,
                        max_chars=settings.RAG_INJECT_MAX_CHARS,
                        query=rq,
                        expand_for_retrieval=expand_hints,
                        condense=settings.RAG_CONDENSE_DOCUMENTS,
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
                        condense=settings.RAG_CONDENSE_DOCUMENTS,
                    )
                    if not ctx:
                        ctx = store.build_all_docs_context(
                            category=category,
                            max_chars=settings.RAG_INJECT_MAX_CHARS,
                            query=rq,
                            expand_for_retrieval=expand_hints,
                            condense=settings.RAG_CONDENSE_DOCUMENTS,
                        )
            rag_meta["context_chars"] = len(ctx) if ctx else 0
            rag_meta["documents_in_prompt"] = ctx.count("### Document :") if ctx else 0
            if ctx:
                prev = rag_meta.get("note")
                rag_meta["context_preview"] = ctx[:900] + ("…" if len(ctx) > 900 else "")
                cap = max(0, int(settings.RAG_ADMIN_FULL_CONTEXT_MAX_CHARS))
                if cap > 0:
                    rag_meta["context_full"] = ctx[:cap]
                else:
                    rag_meta["context_full"] = ctx
                if prev and prev == "category_empty_or_missing":
                    del rag_meta["note"]
            elif category:
                rag_meta.setdefault("note", "no_context_built")
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
            rag_meta["retrieval_error"] = str(exc)
            rag_meta["context_chars"] = 0
            rag_meta["documents_in_prompt"] = 0

        ctx_len = int(rag_meta.get("context_chars") or 0)

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
                        return LLMGenerateResult(
                            text=_vllm_unavailable_message(
                                self._base_url, bucket, after_retries=True
                            ),
                            rag=rag_meta,
                        )
            if resp is None:
                return LLMGenerateResult(
                    text=_vllm_unavailable_message(self._base_url, bucket, after_retries=True),
                    rag=rag_meta,
                )
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
            if (
                ctx
                and ctx_len >= _RAG_REPAIR_MIN_CONTEXT_CHARS
                and claims_absent_in_docs_response(raw)
            ):
                logger.warning(
                    "RAG repair turn: first answer claims missing docs despite %s context chars",
                    ctx_len,
                )
                try:
                    repaired = await self._rag_repair_turn(messages, raw, payload)
                    if repaired:
                        raw = repaired
                        rag_meta["rag_repair"] = True
                except Exception as exc:
                    logger.error("RAG repair turn failed: %s", exc)
            return LLMGenerateResult(
                text=normalize_not_found_response(
                    message, raw, rag_context_chars=ctx_len
                ),
                rag=rag_meta,
            )
        except httpx.HTTPStatusError as exc:
            body = exc.response.text or ""
            if exc.response.status_code == 400 and "maximum context length" in body.lower():
                max_ctx_m = re.search(r"maximum context length is (\d+)", body, flags=re.IGNORECASE)
                in_tok_m = re.search(r"input tokens[^\d]*(\d+)", body, flags=re.IGNORECASE)
                current_max = int(payload.get("max_tokens") or settings.MAX_NEW_TOKENS)
                if max_ctx_m and in_tok_m:
                    max_ctx = int(max_ctx_m.group(1))
                    in_tok = int(in_tok_m.group(1))
                    # Keep a small safety margin for template/system jitter.
                    reduced = max(64, min(current_max, max_ctx - in_tok - 16))
                    if reduced < current_max:
                        logger.warning(
                            "vLLM 400 context overflow; retry with lower max_tokens=%s (was %s, max_ctx=%s, input=%s)",
                            reduced,
                            current_max,
                            max_ctx,
                            in_tok,
                        )
                        payload_retry = dict(payload)
                        payload_retry["max_tokens"] = reduced
                        try:
                            resp2 = await self._client.post("/v1/chat/completions", json=payload_retry)
                            resp2.raise_for_status()
                            data = resp2.json()
                            choice = data["choices"][0]
                            msg = choice.get("message") or {}
                            raw = (msg.get("content") or "").strip()
                            rag_meta["max_tokens_reduced"] = reduced
                            return LLMGenerateResult(
                                text=normalize_not_found_response(
                                    message, raw, rag_context_chars=ctx_len
                                ),
                                rag=rag_meta,
                            )
                        except Exception as retry_exc:
                            logger.error("Retry after context overflow failed: %s", retry_exc)
            logger.error("vLLM HTTP error %s: %s", exc.response.status_code, exc.response.text)
            return LLMGenerateResult(
                text=f"⚠️ Model error ({exc.response.status_code}). Please try again.",
                rag=rag_meta,
            )
        except httpx.ConnectError:
            return LLMGenerateResult(
                text=_vllm_unavailable_message(self._base_url, bucket, after_retries=False),
                rag=rag_meta,
            )
        except Exception as exc:
            logger.error("vLLM request failed: %s", exc, exc_info=True)
            return LLMGenerateResult(
                text=(
                    "⚠️ Unexpected error calling the inference server. "
                    f"If the stack was just restarted, wait for vLLM: `{self._base_url}/v1/models`."
                ),
                rag=rag_meta,
            )

    async def generate_agentic_rag(
        self,
        message: str,
        history: list[dict] | None = None,
        *,
        category: str,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> LLMGenerateResult:
        """Tool-loop retrieval (map search + fetch by id). No DOCUMENTS DE RÉFÉRENCE inject."""
        rag_meta: Dict[str, Any] = {"mode": "agentic_rag", "category": category}

        if not self.available or not self._client:
            rag_meta["note"] = "llm_client_unavailable"
            return LLMGenerateResult(
                text="⚠️ LLM server is not available. Please check vLLM is running on the pod.",
                rag=rag_meta,
            )

        hist = history or []
        bucket = detect_lang_bucket(message)

        if message_contains_profanity(message):
            return LLMGenerateResult(text=POLICY_PROFANITY.get(bucket, POLICY_PROFANITY["fr"]), rag=rag_meta)

        if has_unsupported_script(message):
            return LLMGenerateResult(
                text=POLICY_UNSUPPORTED_LANG.get(bucket, POLICY_UNSUPPORTED_LANG["fr"]),
                rag=rag_meta,
            )

        wrong_lang = unsupported_latin_language_message(message)
        if wrong_lang:
            return LLMGenerateResult(text=wrong_lang, rag=rag_meta)

        if not category:
            rag_meta["note"] = "agentic_missing_category"
            return LLMGenerateResult(
                text="⚠️ Agentic RAG requires a document category.",
                rag=rag_meta,
            )

        store = get_store()
        catalog = build_document_catalog(store, category or "")
        rag_meta["catalog_entries"] = len(catalog)
        if not catalog:
            rag_meta["note"] = "agentic_catalog_empty"
            return LLMGenerateResult(
                text="⚠️ Aucun document disponible dans cette catégorie pour l'agentic RAG.",
                rag=rag_meta,
            )

        agentic_prompt = make_agentic_system_prompt(catalog)
        messages: list[dict] = [{"role": "system", "content": agentic_prompt}]
        for turn in hist:
            role = turn.get("role", "user")
            content = turn.get("content", "")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": message})

        mt = max_tokens or settings.MAX_NEW_TOKENS
        temp = (
            temperature
            if temperature is not None
            else settings.AGENTIC_RAG_TEMPERATURE
        )

        try:
            text, tool_meta = await run_agentic_tool_loop(
                client=self._client,
                model_name=self._model_name,
                base_messages=messages,
                category=category,
                max_tokens=mt,
                temperature=temp,
                top_p=settings.TOP_P,
            )
            rag_meta.update(tool_meta)
            ctx_len = int(rag_meta.get("context_chars") or 0)
            return LLMGenerateResult(
                text=normalize_not_found_response(message, text, rag_context_chars=ctx_len),
                rag=rag_meta,
            )
        except httpx.HTTPStatusError as exc:
            logger.error("vLLM HTTP error (agentic): %s %s", exc.response.status_code, exc.response.text)
            return LLMGenerateResult(
                text=f"⚠️ Model error ({exc.response.status_code}) in agentic mode. Tool calling may be unsupported.",
                rag=rag_meta,
            )
        except httpx.ConnectError:
            return LLMGenerateResult(
                text=_vllm_unavailable_message(self._base_url, bucket, after_retries=True),
                rag=rag_meta,
            )
        except Exception as exc:
            logger.error("Agentic RAG failed: %s", exc, exc_info=True)
            return LLMGenerateResult(
                text="⚠️ Agentic RAG request failed. See server logs.",
                rag=rag_meta,
            )

    async def aclose(self) -> None:
        if self._client:
            await self._client.aclose()
