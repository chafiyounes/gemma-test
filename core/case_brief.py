"""Pre-retrieval case understanding: structured JSON brief for RAG + answer grounding."""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app_config.settings import settings
from core.chat_policy import retrieval_anchor_query

logger = logging.getLogger(__name__)

ACTION_KINDS = frozenset(
    {
        "verify_status",
        "procedure_steps",
        "dispute",
        "ui_howto",
        "general_help",
        "unknown",
    }
)

CASE_BRIEF_SYSTEM_PROMPT = """You are a case-understanding extractor for SENDIT internal logistics support (Morocco).
Staff may write in French, Darija (Arabizi), English, or mixed. Procedure documents are in French.

Your ONLY job: output a single JSON object. Do NOT answer the user. Do NOT recommend procedures.

Rules:
1. Summarize ONLY what appears in the conversation (latest message + history when relevant).
2. user_goal: one sentence — what the staff member wants to accomplish.
3. stated_facts: short bullets of facts explicitly stated by the user (not inferred).
4. do_not_assume: plausible logistics facts that were NOT stated but models often wrongly invent
   (e.g. client refused, livreur failed to deliver, client cancelled by phone) — list each that does NOT apply.
5. retrieval_query_fr: a SHORT French search string for finding SOPs (keywords: statut, colis, vérifier,
   liste des colis, livraison, annulation, etc.). No invented story; no procedure steps.
6. action_kind: one of verify_status | procedure_steps | dispute | ui_howto | general_help | unknown

Output ONLY valid JSON with keys:
user_goal, stated_facts, do_not_assume, retrieval_query_fr, action_kind
""".strip()


@dataclass
class CaseBrief:
    user_goal: str
    stated_facts: List[str] = field(default_factory=list)
    do_not_assume: List[str] = field(default_factory=list)
    retrieval_query_fr: str = ""
    action_kind: str = "unknown"

    def to_metadata(self) -> Dict[str, Any]:
        return asdict(self)


def _extract_json_object(text: str) -> Optional[dict]:
    raw = (text or "").strip()
    if not raw:
        return None
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL | re.IGNORECASE)
    if fence:
        raw = fence.group(1)
    else:
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            raw = raw[start : end + 1]
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        return None


def parse_case_brief_payload(obj: dict) -> Optional[CaseBrief]:
    if not obj:
        return None
    goal = str(obj.get("user_goal") or "").strip()
    if not goal:
        return None
    facts = obj.get("stated_facts")
    if not isinstance(facts, list):
        facts = []
    stated = [str(x).strip() for x in facts if str(x).strip()]
    dna = obj.get("do_not_assume")
    if not isinstance(dna, list):
        dna = []
    do_not = [str(x).strip() for x in dna if str(x).strip()]
    rq = str(obj.get("retrieval_query_fr") or "").strip()
    kind = str(obj.get("action_kind") or "unknown").strip().lower()
    if kind not in ACTION_KINDS:
        kind = "unknown"
    return CaseBrief(
        user_goal=goal[:500],
        stated_facts=stated[:12],
        do_not_assume=do_not[:12],
        retrieval_query_fr=rq[:400],
        action_kind=kind,
    )


def _format_history_for_brief(history: List[dict], *, max_turns: int = 6) -> str:
    lines: List[str] = []
    for turn in (history or [])[-max_turns:]:
        role = turn.get("role", "user")
        content = (turn.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            lines.append(f"{role.upper()}: {content[:1200]}")
    return "\n".join(lines)


def retrieval_query_with_brief(
    message: str,
    history: List[dict] | None,
    brief: Optional[CaseBrief],
) -> str:
    """BM25 query: brief French search string when available, else thread anchor."""
    if brief and (brief.retrieval_query_fr or "").strip():
        return brief.retrieval_query_fr.strip()
    return retrieval_anchor_query(message, history)


def agentic_router_user_content(message: str, brief: Optional[CaseBrief]) -> str:
    """English preamble for the agentic router (latest user turn)."""
    base = (message or "").strip()
    if not brief:
        return base
    facts = "; ".join(brief.stated_facts[:6]) or "(none listed)"
    return (
        f"[Case context for retrieval — do not answer yet]\n"
        f"Goal: {brief.user_goal}\n"
        f"Stated facts: {facts}\n"
        f"French search hint: {brief.retrieval_query_fr or 'n/a'}\n"
        f"action_kind: {brief.action_kind}\n\n"
        f"User message:\n{base}"
    )


async def build_case_brief(
    client: httpx.AsyncClient,
    model_name: str,
    *,
    message: str,
    history: List[dict] | None,
) -> Tuple[Optional[CaseBrief], Dict[str, Any]]:
    """One low-temperature vLLM call; returns (brief, metadata)."""
    meta: Dict[str, Any] = {}
    if not settings.CASE_BRIEF_ENABLED:
        meta["case_brief_skipped_reason"] = "disabled"
        return None, meta
    if not client:
        meta["case_brief_skipped_reason"] = "no_client"
        return None, meta

    anchor = retrieval_anchor_query(message, history or [])
    hist_blob = _format_history_for_brief(history or [])
    user_block = (
        f"Question under discussion (may include prior turn):\n{anchor}\n\n"
        f"Latest message:\n{(message or '').strip()}\n"
    )
    if hist_blob:
        user_block += f"\nRecent conversation:\n{hist_blob}\n"
    user_block += "\nRespond with JSON only."

    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": CASE_BRIEF_SYSTEM_PROMPT},
            {"role": "user", "content": user_block},
        ],
        "max_tokens": settings.CASE_BRIEF_MAX_TOKENS,
        "temperature": settings.CASE_BRIEF_TEMPERATURE,
        "top_p": 0.95,
    }

    t0 = time.perf_counter()
    try:
        resp = await client.post("/v1/chat/completions", json=payload)
        resp.raise_for_status()
        data = resp.json()
        choice = data["choices"][0]
        msg = choice.get("message") or {}
        raw = (msg.get("content") or "").strip()
        meta["case_brief_ms"] = int((time.perf_counter() - t0) * 1000)
        obj = _extract_json_object(raw)
        if not obj:
            meta["case_brief_skipped_reason"] = "invalid_json"
            meta["case_brief_raw_preview"] = raw[:300]
            return None, meta
        brief = parse_case_brief_payload(obj)
        if not brief:
            meta["case_brief_skipped_reason"] = "validation_failed"
            return None, meta
        meta["case_brief"] = brief.to_metadata()
        meta["retrieval_query_fr"] = brief.retrieval_query_fr
        return brief, meta
    except Exception as exc:
        meta["case_brief_ms"] = int((time.perf_counter() - t0) * 1000)
        meta["case_brief_skipped_reason"] = "error"
        meta["case_brief_error"] = str(exc)[:200]
        logger.warning("Case brief failed: %s", exc)
        return None, meta
