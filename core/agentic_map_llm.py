"""LLM extraction of procedure map rows (design doc — map generation worker, sync batch)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Optional

import httpx

from app_config.settings import settings

logger = logging.getLogger(__name__)

MAX_DOC_CHARS = 14_000

MAP_EXTRACTION_PROMPT = """Given the following procedure document written in French, extract a structured
map entry. Respond with JSON only. No preamble. No markdown fences. No explanation.

Document:
{document_text}

Return exactly this structure:
{{
  "id": "{document_id}",
  "title": "short French title describing what this procedure does, max 8 words",
  "tags": ["3 to 6 French keywords a user might search for"],
  "category": "one of: compte, sécurité, accès, facturation, technique, autre"
}}"""


def _strip_json_fence(raw: str) -> str:
    s = raw.strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\s*", "", s)
        s = re.sub(r"\s*```\s*$", "", s)
    return s.strip()


def _parse_json_obj(raw: str) -> Dict[str, Any]:
    text = _strip_json_fence(raw)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            return json.loads(m.group(0))
        raise


def extract_map_entry_llm(
    *,
    document_id: str,
    document_text: str,
    client: httpx.Client,
    model: Optional[str] = None,
    timeout: float = 120.0,
) -> Dict[str, Any]:
    """One vLLM call; retry once on malformed JSON (design doc error handling)."""
    body = (document_text or "")[:MAX_DOC_CHARS]
    sys_prompt = "You output only valid JSON objects. No markdown."
    user_a = MAP_EXTRACTION_PROMPT.format(document_text=body, document_id=document_id)
    user_b = (
        user_a
        + "\n\nYour previous reply was not valid JSON. Output **only** one JSON object, keys: id, title, tags, category."
    )
    mdl = model or (settings.AGENTIC_MAP_EXTRACTION_MODEL or settings.VLLM_MODEL_NAME)

    def one_call(user_content: str) -> Dict[str, Any]:
        payload = {
            "model": mdl,
            "messages": [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_content},
            ],
            "max_tokens": 512,
            "temperature": 0.2,
        }
        r = client.post("/v1/chat/completions", json=payload, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        msg = data["choices"][0].get("message") or {}
        raw = (msg.get("content") or "").strip()
        obj = _parse_json_obj(raw)
        obj["id"] = str(obj.get("id", document_id)).strip() or document_id
        obj["title"] = str(obj.get("title", "")).strip()
        tags = obj.get("tags") or []
        obj["tags"] = [str(t).strip() for t in tags if str(t).strip()][:8]
        obj["category"] = str(obj.get("category", "autre")).strip().lower()
        if not obj["title"]:
            raise ValueError("empty title")
        return obj

    try:
        return one_call(user_a)
    except Exception as first:
        logger.warning("Map extract first pass failed for %s: %s", document_id, first)
        try:
            return one_call(user_b)
        except Exception as second:
            raise RuntimeError(f"LLM map extraction failed for {document_id}: {second}") from second
