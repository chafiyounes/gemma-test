"""Resolve corpus documents for authenticated chat preview."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from core.documents import DOCS_DIR, DOCS_MD_DIR, DocStore

_RE_MD_LINK_LINE = re.compile(
    r"^\s*(?:[-*•]\s+)?\[(?P<label>[^\]]+)\]\((?P<url>[^)]+)\)\s*$"
)
_RE_LINK_HEADING = re.compile(
    r"^\s*(?:#{1,6}\s+)?(?:liens?|voir aussi|related|see also|en savoir plus)\s*:?\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ResolvedDocument:
    category: str
    stem: str


def _normalize_hint(name_hint: str) -> str:
    s = (name_hint or "").strip()
    s = re.sub(r"^[\[\(]+|[\]\)]+$/", "", s).strip()
    for ext in (".docx", ".doc", ".md", ".txt", ".pdf"):
        if s.lower().endswith(ext):
            s = s[: -len(ext)].strip()
    return s


def _category_search_order(store: DocStore, category_hint: Optional[str]) -> List[str]:
    if not category_hint or category_hint.strip().lower() in ("all", "none", "tout"):
        return sorted(store.indexes.keys())
    parts = [p.strip() for p in category_hint.split(",") if p.strip()]
    ordered: List[str] = []
    seen: set[str] = set()
    for p in parts:
        resolved = store.resolve_rag_scope(p)
        for c in resolved:
            if c in store.indexes and c not in seen:
                ordered.append(c)
                seen.add(c)
    for c in sorted(store.indexes.keys()):
        if c not in seen:
            ordered.append(c)
    return ordered


def resolve_document(
    store: DocStore,
    name_hint: str,
    category_hint: Optional[str] = None,
) -> Optional[ResolvedDocument]:
    """Map Source-line free text to indexed ``category`` + ``stem``."""
    raw = _normalize_hint(name_hint)
    if not raw:
        return None

    categories = _category_search_order(store, category_hint)
    raw_lower = raw.lower()

    def scan(cat: str) -> Optional[ResolvedDocument]:
        idx = store.indexes.get(cat)
        if not idx:
            return None
        for doc in idx.docs:
            if doc.name == raw or doc.name.lower() == raw_lower:
                return ResolvedDocument(category=cat, stem=doc.name)
        for doc in idx.docs:
            if raw_lower in doc.name.lower() or doc.name.lower() in raw_lower:
                return ResolvedDocument(category=cat, stem=doc.name)
        return None

    for cat in categories:
        hit = scan(cat)
        if hit:
            return hit
    return None


def _is_link_only_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if _RE_MD_LINK_LINE.match(stripped):
        return True
    if _RE_LINK_HEADING.match(stripped):
        return True
    if re.match(r"^\s*[-*•]\s+\S", stripped) and _RE_MD_LINK_LINE.match(
        re.sub(r"^\s*[-*•]\s+", "", stripped)
    ):
        return True
    return False


def strip_trailing_link_section(md: str) -> str:
    """Remove trailing blocks of markdown-only links (display preview)."""
    if not md or not md.strip():
        return md or ""
    lines = md.split("\n")
    end = len(lines)
    while end > 0:
        line = lines[end - 1]
        if not line.strip():
            end -= 1
            continue
        if _is_link_only_line(line):
            end -= 1
            continue
        break
    return "\n".join(lines[:end]).rstrip()


def _docx_path(category: str, stem: str) -> Path:
    return DOCS_DIR / category / f"{stem}.docx"


def _md_path(category: str, stem: str) -> Path:
    return DOCS_MD_DIR / category / f"{stem}.md"


def build_preview_payload(
    store: DocStore,
    name_hint: str,
    category_hint: Optional[str] = None,
) -> dict:
    resolved = resolve_document(store, name_hint, category_hint)
    if resolved is None:
        raise LookupError(f"Document not found: {name_hint!r}")

    cat, stem = resolved.category, resolved.stem
    docx_path = _docx_path(cat, stem)
    md_path = _md_path(cat, stem)
    has_docx = docx_path.is_file()
    has_md = md_path.is_file()

    markdown = ""
    if has_md:
        try:
            markdown = md_path.read_text(encoding="utf-8")
        except OSError:
            markdown = ""
    if not markdown.strip():
        indexed = store.get_document_by_stem(cat, stem)
        if indexed:
            markdown = indexed

    markdown = strip_trailing_link_section(markdown)

    docx_url: Optional[str] = None
    if has_docx:
        docx_url = f"/api/documents/file/{cat}/{stem}.docx"

    return {
        "resolved_stem": stem,
        "resolved_category": cat,
        "title": stem,
        "has_docx": has_docx,
        "has_md": has_md or bool(markdown.strip()),
        "markdown": markdown,
        "docx_url": docx_url,
    }


def validate_file_request(category: str, filename: str, store: DocStore) -> Tuple[Path, str]:
    """Return (absolute path, media type) for a safe download request."""
    if category not in store.indexes:
        raise LookupError("Unknown category")
    if ".." in filename or "/" in filename or "\\" in filename:
        raise ValueError("Invalid filename")
    lower = filename.lower()
    if lower.endswith(".docx"):
        stem = filename[: -5]
        path = _docx_path(category, stem)
        media = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    elif lower.endswith(".md"):
        stem = filename[: -3]
        path = _md_path(category, stem)
        media = "text/markdown; charset=utf-8"
    else:
        raise ValueError("Unsupported file type")
    if stem != Path(stem).name or not stem:
        raise ValueError("Invalid filename")
    if not path.is_file():
        raise LookupError("File not found")
    return path.resolve(), media
