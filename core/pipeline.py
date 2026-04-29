import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.llm import GemmaModel
from app_config.settings import settings

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    response: str
    model: str = ""
    error: Optional[str] = None


class GemmaPipeline:
    """Thin pipeline: user message → Gemma via vLLM → response.

    No RAG, no translation, no Redis — pure model testing harness.
    The admin can restart vLLM with a different model to compare behaviour.
    """

    def __init__(self) -> None:
        self.llm = GemmaModel()
        self.model_name: str = settings.VLLM_MODEL_NAME
        self.shutdown_requested: bool = False
        logger.info("GemmaPipeline initialised (model=%s)", self.model_name)

    async def process(
        self,
        message: str,
        history: List[Dict[str, str]] | None = None,
        system_prompt: Optional[str] = None,
        category: Optional[str] = None,
    ) -> PipelineResult:
        try:
            response = await self.llm.generate(
                message=message,
                history=history or [],
                system_prompt=system_prompt,
                category=category,
            )
            return PipelineResult(response=response, model=self.model_name)
        except Exception as exc:
            logger.error("Pipeline error: %s", exc, exc_info=True)
            return PipelineResult(
                response="⚠️ An error occurred while generating the response.",
                model=self.model_name,
                error=str(exc),
            )

    async def check_health(self) -> bool:
        return await self.llm.check_health()

    async def aclose(self) -> None:
        await self.llm.aclose()
