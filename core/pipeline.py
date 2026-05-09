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
    rag_meta: Dict[str, Any] = field(default_factory=dict)


class GemmaPipeline:
    """User message → optional RAG (document category) → Gemma via vLLM → response."""

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
            out = await self.llm.generate(
                message=message,
                history=history or [],
                system_prompt=system_prompt,
                category=category,
            )
            return PipelineResult(
                response=out.text,
                model=self.model_name,
                rag_meta=out.rag,
            )
        except Exception as exc:
            logger.error("Pipeline error: %s", exc, exc_info=True)
            return PipelineResult(
                response="⚠️ An error occurred while generating the response.",
                model=self.model_name,
                error=str(exc),
            )

    async def process_agentic(
        self,
        message: str,
        history: List[Dict[str, str]] | None = None,
        category: Optional[str] = None,
    ) -> PipelineResult:
        """Agentic RAG: map + tools; no naive RAG inject."""
        try:
            out = await self.llm.generate_agentic_rag(
                message=message,
                history=history or [],
                category=category or "",
            )
            return PipelineResult(
                response=out.text,
                model=self.model_name,
                rag_meta=out.rag,
            )
        except Exception as exc:
            logger.error("Agentic pipeline error: %s", exc, exc_info=True)
            return PipelineResult(
                response="⚠️ An error occurred in agentic mode.",
                model=self.model_name,
                error=str(exc),
            )

    async def check_health(self) -> bool:
        return await self.llm.check_health()

    async def aclose(self) -> None:
        await self.llm.aclose()
