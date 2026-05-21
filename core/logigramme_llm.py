"""Generate logigrammes from procedure documents via vLLM (SSH/prototype only)."""

from __future__ import annotations

import json
import logging
import re
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import httpx

from app_config.settings import settings
from core.documents import DocStore, get_store

logger = logging.getLogger(__name__)

MAX_DOC_CHARS = 12_000

SUPPORTED_FORMATS = ("mermaid", "dot", "plantuml", "svg", "html", "json_graph")

FORMAT_PROMPTS: Dict[str, str] = {
    "mermaid": """Tu es un expert en logigrammes SENDIT.
Produis UNIQUEMENT un diagramme Mermaid `flowchart TD` en français.
Règles: étapes rectangulaires A[Étape], décisions B{{Question ?}}, fidèle au texte, pas de markdown fence.

Procédure:
{document_text}""",
    "dot": """Tu es un expert en logigrammes SENDIT.
Produis UNIQUEMENT du Graphviz DOT (digraph) en français pour cette procédure.
Format: digraph G {{ node [shape=box]; A -> B; ... }}
Fidèle au texte, pas d'explication.

Procédure:
{document_text}""",
    "plantuml": """Tu es un expert en logigrammes SENDIT.
Produis UNIQUEMENT du PlantUML activity diagram entre @startuml et @enduml, en français.
Fidèle au texte, pas de markdown fence.

Procédure:
{document_text}""",
    "svg": """Tu es un expert en logigrammes SENDIT.
Produis UNIQUEMENT un SVG minimal (rectangles + texte + flèches) représentant la procédure en français.
Balise racine <svg xmlns="http://www.w3.org/2000/svg">. Pas d'explication.

Procédure:
{document_text}""",
    "html": """Tu es un expert en logigrammes SENDIT.
Produis UNIQUEMENT du HTML sémantique pour un flux de procédure:
<div class="flow"><div class="step">...</div>...</div>
Utilise des flèches textuelles ou &rarr; entre étapes. Français. Pas de markdown fence.

Procédure:
{document_text}""",
    "json_graph": """Tu es un expert en logigrammes SENDIT.
Produis UNIQUEMENT un JSON avec cette structure exacte:
{{"nodes":[{{"id":"a","label":"..."}}],"edges":[{{"from":"a","to":"b"}}]}}
Labels en français. Fidèle au texte. Pas de markdown fence.

Procédure:
{document_text}""",
}

FORMAT_RETRY: Dict[str, str] = {
    "mermaid": "Réponds UNIQUEMENT avec flowchart TD valide.",
    "dot": "Réponds UNIQUEMENT avec digraph {{ ... }} valide.",
    "plantuml": "Réponds UNIQUEMENT avec @startuml ... @enduml.",
    "svg": "Réponds UNIQUEMENT avec <svg>...</svg> valide.",
    "html": "Réponds UNIQUEMENT avec <div class=\"flow\">...</div>.",
    "json_graph": "Réponds UNIQUEMENT avec un objet JSON nodes/edges.",
}

FORMAT_SYSTEM: Dict[str, str] = {
    "mermaid": "Tu génères uniquement du code Mermaid valide.",
    "dot": "Tu génères uniquement du Graphviz DOT valide.",
    "plantuml": "Tu génères uniquement du PlantUML valide.",
    "svg": "Tu génères uniquement du SVG valide.",
    "html": "Tu génères uniquement du HTML de flux valide.",
    "json_graph": "Tu génères uniquement du JSON valide.",
}


@dataclass
class GenerationOutcome:
    format: str
    raw: str
    cleaned: str
    syntax_valid: bool
    structure_count: int
    retried: bool
    latency_ms: int
    error: str = ""


def strip_code_fence(raw: str) -> str:
    s = (raw or "").strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\s*", "", s)
        s = re.sub(r"\s*```\s*$", "", s)
    return s.strip()


def validate_mermaid(text: str) -> bool:
    s = strip_code_fence(text)
    if not s:
        return False
    first = s.splitlines()[0].strip().lower()
    return first.startswith("flowchart") or first.startswith("graph ")


def validate_dot(text: str) -> bool:
    s = strip_code_fence(text).lower()
    if "digraph" not in s and "graph " not in s:
        return False
    return "{" in s and "}" in s


def validate_plantuml(text: str) -> bool:
    s = strip_code_fence(text).lower()
    return "@startuml" in s and "@enduml" in s


def validate_svg(text: str) -> bool:
    s = strip_code_fence(text)
    try:
        root = ET.fromstring(s)
    except ET.ParseError:
        return False
    tag = (root.tag or "").lower()
    return tag.endswith("svg")


def validate_html(text: str) -> bool:
    s = strip_code_fence(text).lower()
    return "<div" in s and ("step" in s or "flow" in s)


def validate_json_graph(text: str) -> bool:
    s = strip_code_fence(text)
    try:
        obj = json.loads(s)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", s)
        if not m:
            return False
        try:
            obj = json.loads(m.group(0))
        except json.JSONDecodeError:
            return False
    nodes = obj.get("nodes") if isinstance(obj, dict) else None
    edges = obj.get("edges") if isinstance(obj, dict) else None
    return isinstance(nodes, list) and isinstance(edges, list)


VALIDATORS: Dict[str, Callable[[str], bool]] = {
    "mermaid": validate_mermaid,
    "dot": validate_dot,
    "plantuml": validate_plantuml,
    "svg": validate_svg,
    "html": validate_html,
    "json_graph": validate_json_graph,
}


def count_structure(fmt: str, text: str) -> int:
    s = strip_code_fence(text)
    if fmt == "mermaid":
        return len(re.findall(r"-->|---|-\.->", s))
    if fmt == "dot":
        return len(re.findall(r"->|--", s))
    if fmt == "plantuml":
        return len(re.findall(r":|\bif\b|\bendif\b", s, re.I))
    if fmt == "svg":
        return len(re.findall(r"<rect|<text", s, re.I))
    if fmt == "html":
        return len(re.findall(r'class=["\']step["\']', s, re.I))
    if fmt == "json_graph":
        try:
            obj = json.loads(s)
            return len(obj.get("nodes") or [])
        except Exception:
            return 0
    return 0


def validate_dot_with_binary(text: str) -> bool:
    if not validate_dot(text):
        return False
    s = strip_code_fence(text)
    path = ""
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".dot", delete=False, encoding="utf-8") as f:
            f.write(s)
            path = f.name
        subprocess.run(
            ["dot", "-Tsvg", path, "-o", "/dev/null"],
            capture_output=True,
            timeout=10,
            check=True,
        )
        return True
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return validate_dot(text)
    finally:
        if path:
            try:
                Path(path).unlink()
            except OSError:
                pass


def load_procedure_text(store: DocStore, category: str, stem: str) -> str:
    text = store.get_document_by_stem(category, stem)
    if not text:
        raise ValueError(f"document not found: {category}/{stem}")
    return text


def generate_logigramme(
    *,
    document_text: str,
    fmt: str,
    client: httpx.Client,
    model: Optional[str] = None,
    timeout: float = 120.0,
) -> GenerationOutcome:
    if fmt not in SUPPORTED_FORMATS:
        raise ValueError(f"unsupported format: {fmt}")

    body = (document_text or "")[:MAX_DOC_CHARS]
    user_a = FORMAT_PROMPTS[fmt].format(document_text=body)
    user_b = user_a + "\n\n" + FORMAT_RETRY[fmt]
    mdl = model or settings.VLLM_MODEL_NAME
    validator = VALIDATORS[fmt]
    retried = False
    last_error = ""

    def one_call(user_content: str) -> str:
        payload = {
            "model": mdl,
            "messages": [
                {"role": "system", "content": FORMAT_SYSTEM[fmt]},
                {"role": "user", "content": user_content},
            ],
            "max_tokens": 2048,
            "temperature": 0.25,
        }
        t0 = time.perf_counter()
        r = client.post("/v1/chat/completions", json=payload, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        latency = int((time.perf_counter() - t0) * 1000)
        msg = data["choices"][0].get("message") or {}
        raw = (msg.get("content") or "").strip()
        cleaned = strip_code_fence(raw)
        if not validator(cleaned):
            raise ValueError(f"invalid {fmt} output")
        return raw, cleaned, latency

    try:
        raw, cleaned, latency = one_call(user_a)
    except Exception as exc:
        last_error = str(exc)
        logger.warning("Logigramme %s first pass failed: %s", fmt, exc)
        retried = True
        try:
            raw, cleaned, latency = one_call(user_b)
        except Exception as exc2:
            return GenerationOutcome(
                format=fmt,
                raw="",
                cleaned="",
                syntax_valid=False,
                structure_count=0,
                retried=retried,
                latency_ms=0,
                error=str(exc2),
            )

    syntax = validator(cleaned)
    if fmt == "dot" and syntax:
        syntax = validate_dot_with_binary(cleaned)

    return GenerationOutcome(
        format=fmt,
        raw=raw,
        cleaned=cleaned,
        syntax_valid=syntax,
        structure_count=count_structure(fmt, cleaned),
        retried=retried,
        latency_ms=latency,
        error=last_error if retried and not syntax else "",
    )


# Backward-compatible Mermaid helpers for prototype_logigramme.py
strip_mermaid_fence = strip_code_fence


def generate_logigramme_mermaid(
    *,
    document_text: str,
    client: httpx.Client,
    model: Optional[str] = None,
    timeout: float = 120.0,
) -> str:
    out = generate_logigramme(
        document_text=document_text,
        fmt="mermaid",
        client=client,
        model=model,
        timeout=timeout,
    )
    if not out.syntax_valid:
        raise ValueError(out.error or "invalid mermaid output")
    return out.cleaned
