"""Resolve corpus documents for authenticated chat preview."""
from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Set, Tuple
from urllib.parse import quote

from core.documents import DOCS_DIR, DOCS_MD_DIR, DocStore
from core.logigrammes_store import read as read_logigramme

logger = logging.getLogger(__name__)

_RE_MD_LINK_LINE = re.compile(
    r"^\s*(?:[-*•]\s+)?\[(?P<label>[^\]]+)\]\((?P<url>[^)]+)\)\s*$"
)
_RE_LINK_HEADING = re.compile(
    r"^\s*(?:#{1,6}\s+)?(?:liens?|voir aussi|related|see also|en savoir plus)\s*:?\s*$",
    re.IGNORECASE,
)
_TOKEN_RE = re.compile(r"[A-Za-zÀ-ÿ0-9\u0600-\u06FF]+", re.UNICODE)
_MATCH_MIN_SCORE = 0.38

_RE_DOC_HEADING = re.compile(r"^\s*#+\s*(.+?)\s*$")


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


def _normalize_key(text: str) -> str:
    """Fold accents/punctuation so titles match file stems."""
    if not text:
        return ""
    t = unicodedata.normalize("NFKD", text)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.lower().replace("'", "'").replace("'", "'").replace("–", "-")
    t = re.sub(r"[^a-z0-9\u0600-\u06ff]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _tokens(text: str) -> Set[str]:
    return {t.lower() for t in _TOKEN_RE.findall(text or "")}


def _extract_title_from_text(text: str, max_chars: int = 240) -> str:
    if not text:
        return ""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    for line in lines[:40]:
        s = line.strip()
        if not s:
            continue
        hm = _RE_DOC_HEADING.match(s)
        if hm:
            return (hm.group(1) or "").strip()[:max_chars]
        if (
            len(s) <= max_chars
            and not s.startswith(("-", "*", "|", "["))
            and not re.match(r"^\d+[\.)]\s", s)
        ):
            return s[:max_chars]
    return ""


def _match_score(hint: str, *candidates: str) -> float:
    if not hint:
        return 0.0
    hint_norm = _normalize_key(hint)
    hint_toks = _tokens(hint)
    if not hint_toks:
        return 0.0
    best = 0.0
    for cand in candidates:
        if not cand:
            continue
        cand_norm = _normalize_key(cand)
        if hint_norm and cand_norm:
            if hint_norm == cand_norm:
                return 1.0
            if hint_norm in cand_norm or cand_norm in hint_norm:
                best = max(best, 0.9)
        ct = _tokens(cand)
        if not ct:
            continue
        overlap = len(hint_toks & ct) / len(hint_toks)
        best = max(best, overlap)
    return best


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
    # Answers may cite help_md articles while chat scope was procedures-only.
    from app_config.settings import settings  # noqa: PLC0415

    extra_raw = (settings.RAG_EXTRA_CATEGORIES or "").strip()
    if extra_raw:
        for alias in extra_raw.split(","):
            alias = alias.strip()
            if not alias:
                continue
            for c in store.resolve_rag_scope(alias):
                if c in store.indexes and c not in seen:
                    ordered.append(c)
                    seen.add(c)
    for c in sorted(store.indexes.keys()):
        if c not in seen:
            ordered.append(c)
    return ordered


def _best_from_docs(
    raw: str,
    categories: List[str],
    store: DocStore,
) -> Tuple[Optional[ResolvedDocument], float]:
    best: Optional[ResolvedDocument] = None
    best_score = 0.0
    raw_lower = raw.lower()

    for cat in categories:
        idx = store.indexes.get(cat)
        if not idx:
            continue
        for doc in idx.docs:
            title = _extract_title_from_text(doc.text)
            score = _match_score(
                raw,
                doc.name,
                Path(doc.name).stem,
                title,
            )
            if doc.name == raw or doc.name.lower() == raw_lower:
                score = max(score, 1.0)
            if score > best_score:
                best_score = score
                best = ResolvedDocument(category=cat, stem=doc.name)
    return best, best_score


def _best_from_disk(
    raw: str,
    categories: List[str],
) -> Tuple[Optional[ResolvedDocument], float]:
    best: Optional[ResolvedDocument] = None
    best_score = 0.0

    for cat in categories:
        for base in (DOCS_DIR / cat, DOCS_MD_DIR / cat):
            if not base.is_dir():
                continue
            for pattern in ("*.docx", "*.md"):
                for p in base.rglob(pattern):
                    try:
                        rel = p.relative_to(base).with_suffix("")
                        stem = rel.as_posix()
                    except ValueError:
                        stem = p.stem
                    score = _match_score(raw, stem, p.stem)
                    if score > best_score:
                        best_score = score
                        best = ResolvedDocument(category=cat, stem=stem)
    return best, best_score


def resolve_document(
    store: DocStore,
    name_hint: str,
    category_hint: Optional[str] = None,
) -> Optional[ResolvedDocument]:
    """Map Source-line free text (title or filename) to ``category`` + ``stem``."""
    raw = _normalize_hint(name_hint)
    if not raw:
        return None

    categories = _category_search_order(store, category_hint)
    hit, score = _best_from_docs(raw, categories, store)
    if score < _MATCH_MIN_SCORE:
        disk_hit, disk_score = _best_from_disk(raw, categories)
        if disk_score > score:
            hit, score = disk_hit, disk_score

    if hit and score >= _MATCH_MIN_SCORE:
        logger.debug(
            "document_preview resolved %r -> %s/%s (score=%.2f)",
            name_hint,
            hit.category,
            hit.stem,
            score,
        )
        return hit
    logger.info(
        "document_preview no match for %r (best_score=%.2f, categories=%s)",
        name_hint,
        score,
        categories,
    )
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


def _docx_candidates(category: str, stem: str) -> List[Path]:
    cat_dir = DOCS_DIR / category
    out: List[Path] = []
    direct = cat_dir / f"{stem}.docx"
    if direct.is_file():
        out.append(direct)
    alt = (cat_dir / stem).with_suffix(".docx")
    if alt.is_file() and alt not in out:
        out.append(alt)
    if cat_dir.is_dir():
        stem_norm = _normalize_key(stem)
        for p in cat_dir.rglob("*.docx"):
            if _normalize_key(p.stem) == stem_norm or _normalize_key(p.stem) == _normalize_key(
                Path(stem).name
            ):
                if p not in out:
                    out.append(p)
    return out


def _md_candidates(category: str, stem: str) -> List[Path]:
    md_cat = DOCS_MD_DIR / category
    out: List[Path] = []
    direct = md_cat / f"{stem}.md"
    if direct.is_file():
        out.append(direct)
    alt = (md_cat / stem).with_suffix(".md")
    if alt.is_file() and alt not in out:
        out.append(alt)
    if md_cat.is_dir():
        stem_norm = _normalize_key(stem)
        for p in md_cat.rglob("*.md"):
            if _normalize_key(p.relative_to(md_cat).with_suffix("").as_posix()) == stem_norm:
                if p not in out:
                    out.append(p)
    return out


def _locate_docx(category: str, stem: str) -> Optional[Path]:
    cands = _docx_candidates(category, stem)
    return cands[0] if cands else None


def _locate_md(category: str, stem: str) -> Optional[Path]:
    cands = _md_candidates(category, stem)
    return cands[0] if cands else None


def _file_download_url(category: str, path: Path) -> str:
    """URL-safe path for stems with spaces, accents, or subfolders."""
    try:
        rel = path.relative_to(DOCS_DIR / category)
        filename = rel.as_posix()
    except ValueError:
        filename = path.name
    return f"/api/documents/file/{quote(category, safe='')}/{quote(filename, safe='')}"


def build_preview_payload(
    store: DocStore,
    name_hint: str,
    category_hint: Optional[str] = None,
) -> dict:
    resolved = resolve_document(store, name_hint, category_hint)
    if resolved is None:
        raise LookupError(f"Document not found: {name_hint!r}")

    cat, stem = resolved.category, resolved.stem
    docx_path = _locate_docx(cat, stem)
    md_path = _locate_md(cat, stem)
    has_docx = docx_path is not None and docx_path.is_file()
    has_md = md_path is not None and md_path.is_file()

    markdown = ""
    if has_md and md_path is not None:
        try:
            markdown = md_path.read_text(encoding="utf-8")
        except OSError:
            markdown = ""
    if not markdown.strip():
        indexed = store.get_document_by_stem(cat, stem)
        if indexed:
            markdown = indexed

    markdown = strip_trailing_link_section(markdown)
    display_title = _extract_title_from_text(markdown) or name_hint.strip() or stem

    docx_url: Optional[str] = None
    if has_docx and docx_path is not None:
        docx_url = _file_download_url(cat, docx_path)

    logigramme = read_logigramme(cat, stem) or ""
    has_logigramme = bool(logigramme.strip())

    return {
        "resolved_stem": stem,
        "resolved_category": cat,
        "title": display_title,
        "has_docx": has_docx,
        "has_md": has_md or bool(markdown.strip()),
        "has_logigramme": has_logigramme,
        "markdown": markdown,
        "logigramme": logigramme,
        "docx_url": docx_url,
    }


def validate_file_request(category: str, filename: str, store: DocStore) -> Tuple[Path, str]:
    """Return (absolute path, media type) for a safe download request."""
    if category not in store.indexes:
        # Allow download when category folder exists on disk (edge case after partial index)
        if not (DOCS_DIR / category).is_dir() and not (DOCS_MD_DIR / category).is_dir():
            raise LookupError("Unknown category")
    fn = (filename or "").replace("\\", "/").lstrip("/")
    if ".." in fn.split("/"):
        raise ValueError("Invalid filename")
    lower = fn.lower()
    if lower.endswith(".docx"):
        stem = fn[: -5]
        path = _locate_docx(category, stem)
        media = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    elif lower.endswith(".md"):
        stem = fn[: -3]
        path = _locate_md(category, stem)
        media = "text/markdown; charset=utf-8"
    else:
        raise ValueError("Unsupported file type")
    if not stem or Path(stem).name != Path(stem).as_posix().split("/")[-1]:
        pass  # subpaths allowed
    if path is None or not path.is_file():
        # Last resort: direct path under category
        fallback = (DOCS_DIR / category / fn) if lower.endswith(".docx") else (DOCS_MD_DIR / category / fn)
        if fallback.is_file():
            path = fallback
        else:
            raise LookupError("File not found")
    return path.resolve(), media
