"""
Convert Word `.docx` body to GitHub-flavoured Markdown for RAG.

**In scope (main document body only)**:
- Paragraphs → Markdown blocks (headings from Word styles when possible).
- Tables → pipe tables; cell text preserves line breaks; ``|`` escaped.
- Soft line breaks (Shift+Enter) inside a paragraph → single newline.

**Out of scope (ignored)**:
- Headers, footers, and watermarks — not part of ``word/document.xml`` body; untyped.
- Images, shapes, embedded logos — no placeholder; paragraphs that only contain drawings emit nothing.
- Text boxes anchored outside normal flow may not always appear (Word OOXML limitation).

See: ``python -m scripts.export_sop_to_md`` to batch ``data/documents/<cat>/*.docx`` → ``data/documents_md/<cat>/*.md``.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import List

from core.sop_text_clean import clean_sop_markdown

logger = logging.getLogger(__name__)

_HEADER_TABLE_KEYWORDS = {
    "titre", "référence", "reference", "version",
    "date d'application", "date d\u2019application",
    "domaine d'application", "domaine d\u2019application",
    "responsable",
}
_FOOTER_TABLE_KEYWORDS = {
    "rédigé par", "redige par", "réalisé par", "realise par",
    "vérifié par", "verifie par", "approuvé par", "approuve par",
    "validé par", "valide par",
}


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
            cell_texts.append(_paragraphs_text_in_cell(cell))
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


def _paragraphs_text_in_cell(cell_xml) -> str:
    """Join all w:p in a table cell (handles nested paragraph structure)."""
    from docx.oxml.ns import qn

    parts: List[str] = []
    for p in cell_xml.findall(qn("w:p")):
        t = _paragraph_element_plain(p)
        if t:
            parts.append(t)
    return "\n".join(parts).strip()


def _paragraph_element_plain(p_xml) -> str:
    """Text + line breaks for one ``w:p`` (body or table). Drawings produce no ``w:t``."""
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
            first_cols.append(parts[0].lower())
    all_kw = _HEADER_TABLE_KEYWORDS | _FOOTER_TABLE_KEYWORDS
    matches = sum(1 for v in first_cols if v in all_kw)
    return matches >= 2 or (bool(first_cols) and matches / len(first_cols) >= 0.5)


def _ordered_body_chunks(doc) -> List[str]:
    """Body-order blocks: paragraphs (as heading or plain) and non-metadata tables."""
    from docx.oxml.ns import qn
    try:
        from docx.text.paragraph import Paragraph
    except ImportError:
        Paragraph = None  # type: ignore

    body = doc.element.body
    out: List[str] = []
    for child in body:
        tag = child.tag.split("}")[-1]
        if tag == "p":
            text = _paragraph_element_plain(child)
            if not text:
                continue
            prefix = ""
            if Paragraph is not None:
                try:
                    p = Paragraph(child, doc)
                    st = p.style.name if p.style else "Normal"
                    prefix = _md_heading_prefix_for_style(st)
                except Exception:
                    prefix = ""
            line = f"{prefix}{text}" if prefix else text
            out.append(line)
        elif tag == "tbl":
            md = _table_to_markdown(child)
            if md and not _is_metadata_markdown_table(md):
                out.append(md)
    return out


def convert_docx_to_markdown(path: Path | str) -> str:
    """Parse ``.docx`` main body to Markdown; drop boilerplate tables; clean SOP cruft."""
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
