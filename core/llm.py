import logging
from typing import Optional

import httpx

from app_config.settings import settings
from core.documents import get_store

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Tu es l'assistant IA officiel de SENDIT, une entreprise marocaine de logistique et de livraison.
Ton rôle est de répondre avec une PRÉCISION ABSOLUE aux questions des collaborateurs concernant les procédures internes (SOP).

CONTEXTE FOURNI :
Ci-dessous, tu recevras le texte intégral de plusieurs documents de référence. Chaque document commence par "### Document : [Nom]".

INSTRUCTIONS CRITIQUES :
1. EXACTITUDE : Ta réponse doit s'appuyer **UNIQUEMENT** sur les documents fournis. Ne fais aucune supposition et n'ajoute aucune information externe.
2. CITATION : Si tu trouves la réponse, tu **DOIS OBLIGATOIREMENT** citer le nom exact du document source à la fin de ta réponse (ex: "Source : [Nom du document]").
3. HORS SUJET / INTROUVABLE : Si la réponse ne se trouve dans AUCUN des documents fournis, tu dois répondre EXACTEMENT ceci : "Je n'ai pas trouvé cette information dans les procédures actuellement disponibles." Ne tente pas de deviner.
4. FORMAT : Sois clair, direct et structuré. Utilise des listes à puces pour les règles, ou des étapes numérotées pour les procédures. Ne fais pas d'introductions inutiles.
5. EXHAUSTIVITÉ : Si la question porte sur une liste (ex: produits interdits), fournis la liste complète telle qu'elle apparaît dans le document de référence.

LANGUES ET STYLE :
- Réponds par défaut en **Français** (langue des procédures).
- Si l'utilisateur pose la question en **Anglais**, réponds en Anglais.
- Si l'utilisateur pose la question en **Darija marocaine** (en caractères arabes ou en Arabizi comme "kifash", "ch7al"), réponds de manière claire et professionnelle dans la même langue.
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

        sys_prompt = (system_prompt or SYSTEM_PROMPT).strip()

        # Inject ALL SOP documents from the chosen category into the context
        # so the model always has the full set of procedure documents available.
        try:
            ctx = get_store().build_all_docs_context(category=category, max_chars=60000)
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

        # Append prior turns from the conversation history
        for turn in (history or []):
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
            return data["choices"][0]["message"]["content"].strip()
        except httpx.HTTPStatusError as exc:
            logger.error("vLLM HTTP error %s: %s", exc.response.status_code, exc.response.text)
            return f"⚠️ Model error ({exc.response.status_code}). Please try again."
        except Exception as exc:
            logger.error("vLLM request failed: %s", exc)
            return "⚠️ Failed to reach the model server. Please check connectivity."

    async def aclose(self) -> None:
        if self._client:
            await self._client.aclose()
