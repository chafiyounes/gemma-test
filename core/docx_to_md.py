"""
Convert Word `.docx` main body to GitHub-flavoured Markdown for RAG.

Serialises the **entire document body** in order: headings, paragraphs (including
simple lists), and **all** tables (including cells that contain nested tables).
Boilerplate author/validation tables are still removed in a final cleanup pass
via ``clean_sop_markdown`` where they match author keywords.

**In scope (``word/document.xml`` body)**:
- Paragraphs with heading styles (Title / Titre / Heading n).
- List paragraphs (numPr or style name containing "list") as ``- `` bullets with indent.
- Tables as GFM pipe tables; ``|`` escaped in cells; line breaks as ``<br>``.

**Out of scope**:
- Headers, footers (different OOXML parts).
- Images / logos: no output unless there is visible text in the paragraph.

See: ``python -m scripts.export_sop_to_md`` for batch export.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import List, Optional

from core.sop_text_clean import clean_sop_markdown

logger = logging.getLogger(__name__)

_HEADER_TABLE_KEYWORDS = frozenset({
    "titre", "référence", "reference", "version",
    "date d'application", "date d\u2019application",
    "domaine d'application", "domaine d\u2019application",
    "responsable",
})
_FOOTER_TABLE_KEYWORDS = frozenset({
    "rédigé par", "redige par", "réalisé par", "realise par",
    "vérifié par", "verifie par", "approuvé par", "approuve par",
    "validé par", "valide par",
})


def _drop_metadata_tables_setting() -> bool:
    try:
        from app_config.settings import settings

        return bool(getattr(settings, "DOCX_MD_DROP_METADATA_TABLES", False))
    except Exception:
        return False


def _escape_cell(text: str) -> str:
    t = text.replace("\r\n", "\n").replace("\r", "\n")
    t = t.replace("|", "\\|")
    t = re.sub(r"\n+", "<br>", t)
    return t


def _table_to_markdown(table_xml) -> str:
    from docx.oxml.ns import qn

    rows = table_xml.findall(qn("w:tr"))
    if not rows:
        return ""

    parsed_rows: List[List[str]] = []
    for row in rows:
        cells = row.findall(qn("w:tc"))
        cell_texts = []
        for cell in cells:
            cell_texts.append(_cell_content_markdown(cell))
        parsed_rows.append(cell_texts)

    if not parsed_rows:
        return ""

    headers = [_escape_cell(c) for c in parsed_rows[0]]
    data_rows = [[_escape_cell(c) for c in r] for r in parsed_rows[1:]]
    col_widths: List[int] = []
    for i, h in enumerate(headers):
        max_w = len(h)
        for r in data_rows:
            if i < len(r):
                max_w = max(max_w, len(r[i]))
        col_widths.append(max(max_w, 3))

    lines: List[str] = []
    lines.append("| " + " | ".join(h.ljust(w) for h, w in zip(headers, col_widths)) + " |")
    lines.append("| " + " | ".join("-" * w for w in col_widths) + " |")
    for row in data_rows:
        padded = []
        for i, w in enumerate(col_widths):
            val = row[i] if i < len(row) else ""
            padded.append(val.ljust(w))
        lines.append("| " + " | ".join(padded) + " |")
    return "\n".join(lines)


def _cell_content_markdown(cell_xml) -> str:
    """Ordered content inside a cell: paragraphs and nested tables."""
    from docx.oxml.ns import qn

    parts: List[str] = []
    for child in cell_xml:
        tag = child.tag.split("}")[-1]
        if tag == "p":
            t = _paragraph_element_plain(child)
            if t:
                parts.append(t)
        elif tag == "tbl":
            nested = _table_to_markdown(child)
            if nested:
                parts.append(nested)
    return "\n\n".join(parts).strip()


def _paragraph_element_plain(p_xml) -> str:
    """Text + soft breaks; drawings without ``w:t`` yield empty."""
    buf: List[str] = []
    for child in p_xml:
        for sub in child.iter():
            tag = sub.tag.split("}")[-1]
            if tag == "t" and sub.text:
                buf.append(sub.text)
            elif tag == "br":
                buf.append("\n")
            elif tag == "tab":
                buf.append("\t")
    return "".join(buf).strip()


def _list_markdown_prefix(p_xml) -> str:
    from docx.oxml.ns import qn

    p_pr = p_xml.find(qn("w:pPr"))
    if p_pr is None:
        return ""
    num_pr = p_pr.find(qn("w:numPr"))
    if num_pr is None:
        return ""
    ilvl_el = num_pr.find(qn("w:ilvl"))
    level = 0
    if ilvl_el is not None:
        v = ilvl_el.get(qn("w:val"))
        if v is not None:
            try:
                level = int(v)
            except ValueError:
                level = 0
    indent = "  " * max(0, min(level, 8))
    return f"{indent}- "


def _md_heading_prefix_for_style(style_name: str) -> str:
    s = (style_name or "Normal").strip()
    if s in ("Title", "Titre", "Document Title"):
        return "# "
    for pat in (r"^heading\s*(\d+)$", r"^titre\s*(\d+)$"):
        m = re.match(pat, s, re.IGNORECASE)
        if m:
            n = min(int(m.group(1)), 6)
            return "#" * n + " "
    m2 = re.match(r"^toc\s*heading", s, re.IGNORECASE)
    if m2:
        return "## "
    return ""


def _is_metadata_markdown_table(md: str) -> bool:
    lines = [ln for ln in md.splitlines() if ln.strip().startswith("|")]
    if len(lines) < 2:
        return False
    first_cols: List[str] = []
    for ln in lines:
        parts = [p.strip() for p in ln.strip().strip("|").split("|")]
        parts = [p.replace("\\|", "|") for p in parts]
        if parts:
            c0 = parts[0].lower()
            if "<br>" in c0:
                c0 = c0.split("<br>", 1)[0].strip()
            first_cols.append(c0)
    all_kw = _HEADER_TABLE_KEYWORDS | _FOOTER_TABLE_KEYWORDS
    matches = sum(1 for v in first_cols if v in all_kw)
    return matches >= 2 or (bool(first_cols) and matches / len(first_cols) >= 0.5)


def _body_paragraph_as_markdown(doc, p_xml, Paragraph) -> Optional[str]:
    text = _paragraph_element_plain(p_xml)
    if not text:
        return None
    heading_prefix = ""
    style_name = "Normal"
    try:
        p = Paragraph(p_xml, doc)
        style_name = p.style.name if p.style else "Normal"
        heading_prefix = _md_heading_prefix_for_style(style_name)
    except Exception:
        pass

    if heading_prefix:
        return f"{heading_prefix}{text}"

    lp = _list_markdown_prefix(p_xml)
    if lp:
        return f"{lp}{text}"
    if style_name and "list" in style_name.lower():
        alt = _list_markdown_prefix(p_xml) or "- "
        return f"{alt}{text}"
    return text


def _ordered_body_chunks(doc) -> List[str]:
    from docx.oxml.ns import qn
    try:
        from docx.text.paragraph import Paragraph
    except ImportError:
        Paragraph = None  # type: ignore

    body = doc.element.body
    out: List[str] = []
    Paragraph_cls = Paragraph

    for child in body:
        tag = child.tag.split("}")[-1]
        if tag == "p":
            if Paragraph_cls is None:
                t = _paragraph_element_plain(child)
                if t:
                    out.append(t)
            else:
                line = _body_paragraph_as_markdown(doc, child, Paragraph_cls)
                if line:
                    out.append(line)
        elif tag == "tbl":
            md = _table_to_markdown(child)
            if not md:
                continue
            if _drop_metadata_tables_setting() and _is_metadata_markdown_table(md):
                continue
            out.append(md)
    return out


def convert_docx_to_markdown(path: Path | str) -> str:
    """Parse ``.docx`` main body to Markdown; clean SOP cruft (images, author tables)."""
    try:
        from docx import Document
    except ImportError:
        return ""

    path = Path(path)
    try:
        doc = Document(str(path))
        chunks = _ordered_body_chunks(doc)
        raw = "\n\n".join(chunks)
        return clean_sop_markdown(raw)
    except Exception as exc:
        logger.warning("docx_to_md: failed for %s: %s", path, exc)
        return ""


def export_category(
    category_dir: Path,
    out_dir: Path,
    *,
    dry_run: bool = False,
) -> int:
    """Write one category folder of ``.docx`` to ``out_dir`` as ``.md``."""
    n = 0
    for docx in sorted(category_dir.glob("*.docx")):
        text = convert_docx_to_markdown(docx)
        if not text.strip():
            continue
        out_path = out_dir / f"{docx.stem}.md"
        if dry_run:
            print(f"would write {out_path} ({len(text)} chars)")
        else:
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path.write_text(text, encoding="utf-8")
            print(f"wrote {out_path}")
        n += 1
    return n
