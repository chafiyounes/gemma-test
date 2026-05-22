"""Shared Mermaid validation/normalization (no DocStore imports)."""

from __future__ import annotations

import re

_INIT_DIRECTIVE_RE = re.compile(r"^%%\{init:[\s\S]*?\}%%\s*$", re.IGNORECASE)


def strip_code_fence(raw: str) -> str:
    s = (raw or "").strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\s*", "", s)
        s = re.sub(r"\s*```\s*$", "", s)
    return s.strip()


def _is_graph_header(line: str) -> bool:
    low = (line or "").strip().lower()
    return low.startswith("flowchart") or low.startswith("graph ")


def _skip_preamble_lines(lines: list[str]) -> list[str]:
    out: list[str] = []
    skipping = True
    for line in lines:
        stripped = line.strip()
        if skipping:
            if not stripped:
                continue
            if _INIT_DIRECTIVE_RE.match(stripped):
                continue
            if stripped.startswith("%%") and not _is_graph_header(stripped):
                continue
            skipping = False
        out.append(line)
    return out


def normalize_mermaid(text: str) -> str:
    """Strip fences/init preamble; first substantive line should be flowchart/graph."""
    s = strip_code_fence(text)
    if not s:
        return ""
    lines = _skip_preamble_lines(s.splitlines())
    return "\n".join(lines).strip()


def validate_mermaid(text: str) -> bool:
    s = normalize_mermaid(text)
    if not s:
        return False
    for line in s.splitlines()[:8]:
        if _is_graph_header(line):
            return True
    return False
