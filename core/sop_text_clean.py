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


# Markdown `![alt](url)` — model must not receive embed semantics or base64 payloads.
_RE_MD_IMAGE = re.compile(r"!\[(?P<alt>[^\]]*)\]\((?P<url>[^)]+)\)")
# HTML <img …> — strip tags; keep a short src hint when safe (not data: blobs).
_RE_HTML_IMG_OPEN = re.compile(r"<img\b[^>]*?>", re.IGNORECASE | re.DOTALL)
_RE_HTML_SRC = re.compile(r"\bsrc\s*=\s*[\"']([^\"']+)[\"']", re.IGNORECASE)


def normalize_markdown_images_for_llm(text: str) -> str:
    """Turn `![alt](url)` into non-embedding `[Figure — alt](url)`; drop huge/data URLs."""

    def repl(m: re.Match[str]) -> str:
        alt = (m.group("alt") or "").strip() or "image"
        url = (m.group("url") or "").strip()
        low = url.lower()
        if low.startswith("data:"):
            return f"[Figure - {alt}](inline-image-omitted)"
        if len(url) > 480:
            url = url[:240] + "..." + url[-120:]
        return f"[Figure - {alt}]({url})"

    return _RE_MD_IMAGE.sub(repl, text)


def replace_html_img_tags_with_placeholders(text: str) -> str:
    """Remove `<img>` tags; never pass embedded image data into the RAG prompt."""

    def one_tag(tag: str) -> str:
        sm = _RE_HTML_SRC.search(tag)
        src = (sm.group(1) or "").strip() if sm else ""
        if not src:
            return "(image)"
        low = src.lower()
        if low.startswith("data:"):
            return "(image inline omise)"
        if len(src) > 180:
            src = src[:177] + "..."
        return f"(image : {src})"

    return _RE_HTML_IMG_OPEN.sub(lambda m: one_tag(m.group(0)), text)


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


def strip_sections_after_numbered_heads(text: str, max_section: int = 5) -> str:
    """Drop content from the first heading that looks like section ``max_section+1`` … 7.

    Typical SOPs are numbered 1–7. With ``max_section=5``, anything from sections
    **6** and **7** onward is removed when a line looks like ``6. Title``,
    ``## 7) …``, or ``Section 6 …``. Set ``SOP_MAX_SECTION_TO_KEEP`` to ``0``
    in settings to disable.
    """
    if max_section <= 0 or not text.strip():
        return text

    start_drop = max_section + 1
    tail_nums = list(range(start_drop, 8))
    if not tail_nums:
        return text

    nums_alt = "|".join(str(n) for n in tail_nums)
    dotted = re.compile(
        rf"(?m)^(?:(#{{1,6}})\s+)?({nums_alt})[\.\)]\s*(?:\S.*)?$"
    )
    named = re.compile(
        rf"(?m)^(?:(#{{1,6}})\s+)?(?:Section|SECTION)\s+({nums_alt})\b.*$"
    )

    candidates: list[int] = []
    for pat in (dotted, named):
        m = pat.search(text)
        if m:
            candidates.append(m.start())
    if not candidates:
        return text
    cut = min(candidates)
    return text[:cut].rstrip()


def clean_sop_markdown(text: str) -> str:
    """What we apply to any src=md/txt/docx convert before indexing."""
    text = normalize_markdown_images_for_llm(text)
    text = replace_html_img_tags_with_placeholders(text)
    text = strip_author_tables(strip_image_markers(text))
    try:
        from app_config.settings import settings

        cap = int(getattr(settings, "SOP_MAX_SECTION_TO_KEEP", 0) or 0)
    except Exception:
        cap = 0
    if cap > 0:
        text = strip_sections_after_numbered_heads(text, max_section=cap)
    return text
