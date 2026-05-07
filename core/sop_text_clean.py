"""Post-processing shared by RAG sources: .md / .txt exports and docx pipeline."""
from __future__ import annotations

import re

_AUTHOR_TEXT_KEYWORDS = [
    "rédigé par", "redige par", "réalisé par", "realise par",
    "vérifié par", "verifie par", "approuvé par", "approuve par",
    "validé par", "valide par",
]


def collapse_whitespace(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def strip_image_markers(text: str) -> str:
    text = re.sub(r"\[\[IMAGE:[^\]]+\]\]", "", text, flags=re.IGNORECASE)
    return collapse_whitespace(text)


def strip_author_tables(text: str) -> str:
    """Remove markdown table blocks that look like author/validation footers."""
    lines = text.split("\n")
    result: list[str] = []
    table_block: list[str] = []
    in_table = False

    for line in lines:
        if line.strip().startswith("|"):
            in_table = True
            table_block.append(line)
        else:
            if in_table:
                block_lower = "\n".join(table_block).lower()
                if any(kw in block_lower for kw in _AUTHOR_TEXT_KEYWORDS):
                    pass
                else:
                    result.extend(table_block)
                table_block = []
                in_table = False
            result.append(line)
    if in_table and table_block:
        block_lower = "\n".join(table_block).lower()
        if not any(kw in block_lower for kw in _AUTHOR_TEXT_KEYWORDS):
            result.extend(table_block)
    return collapse_whitespace("\n".join(result))


def clean_sop_markdown(text: str) -> str:
    """What we apply to any src=md/txt/docx convert before indexing."""
    return strip_author_tables(strip_image_markers(text))
