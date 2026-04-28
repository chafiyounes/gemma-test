import logging
from typing import Optional

import httpx

from app_config.settings import settings
from core.documents import get_store

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Tu es un assistant IA expert pour une entreprise marocaine de logistique et livraison (Sendit).
Tu réponds aux questions sur les procédures internes (SOP) en t'appuyant STRICTEMENT sur les documents fournis ci-dessous.

Langues supportées :
- Français (langue principale des procédures)
- English
- Darija marocaine (caractères arabes)
- Arabizi (Darija en caractères latins avec chiffres : kif dayr, 3lash, mzyan…)

Règles :
1. Si la réponse se trouve dans les documents : cite le nom du document concerné.
2. Si la réponse N'EST PAS dans les documents : dis-le clairement, ne fabrique rien.
3. Réponds dans la langue de la question.
4. Sois concis, précis, et professionnel."""


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
    ) -> str:
        """Call the vLLM OpenAI-compatible chat completions endpoint."""
        if not self.available or not self._client:
            return "⚠️ LLM server is not available. Please check vLLM is running on the pod."

        sys_prompt = (system_prompt or SYSTEM_PROMPT).strip()

        # Inject top-K SOP documents relevant to the user's question
        try:
            ctx = get_store().build_context(message, k=5, max_chars=12000)
            if ctx:
                sys_prompt = (
                    sys_prompt
                    + "\n\n--- DOCUMENTS DE RÉFÉRENCE (procédures internes) ---\n"
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
