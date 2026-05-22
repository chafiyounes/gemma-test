from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from app_config.settings import settings
from core.documents import DOCS_DIR, DOCS_MD_DIR, DOCS_TXT_DIR, _read_docx, _read_md, _read_txt
from core.docx_to_md import convert_docx_to_markdown
from core.logigrammes_store import draft_exists as logigramme_draft_exists
from core.logigrammes_store import exists as logigramme_exists

logger = logging.getLogger(__name__)

_SAFE_RE = re.compile(r"[^A-Za-z0-9._\- ]+")


class DocumentAdminError(Exception):
    pass


def _sanitize_segment(value: str, *, field_name: str) -> str:
    raw = (value or "").strip()
    if not raw:
        raise DocumentAdminError(f"{field_name} is required")
    cleaned = _SAFE_RE.sub("_", raw).strip("._ ")
    if not cleaned:
        raise DocumentAdminError(f"{field_name} is invalid")
    return cleaned


def _reject_unsafe_basename(name: str) -> str:
    """Basename only; reject path components that could escape the corpus folder."""
    raw = (name or "").strip()
    if not raw:
        raise DocumentAdminError("filename is required")
    if ".." in raw or "/" in raw or "\\" in raw:
        raise DocumentAdminError("Invalid filename")
    return raw


def _resolve_file_under_dir(dir_path: Path, filename: str, *, hint: str = "") -> Path:
    """Resolve a file under dir_path to an existing Path.

    Overview lists real ``p.name`` values from disk; ``_sanitize_segment`` can
    diverge (e.g. accents → underscores). Deletes/moves must match on-disk names.
    """
    raw = _reject_unsafe_basename(filename)
    if not dir_path.is_dir():
        raise DocumentAdminError(f"File not found{': ' + hint if hint else ''}")
    base = dir_path.resolve()

    p = (dir_path / raw).resolve()
    if p.is_file() and p.parent.resolve() == base:
        return p

    try:
        safe = _sanitize_segment(raw, field_name="filename")
    except DocumentAdminError:
        safe = ""

    if safe and safe != raw:
        p2 = (dir_path / safe).resolve()
        if p2.is_file() and p2.parent.resolve() == base:
            return p2

    matches: List[Path] = []
    for c in dir_path.iterdir():
        if not c.is_file():
            continue
        if c.parent.resolve() != base:
            continue
        if c.name == raw or (safe and c.name == safe):
            matches.append(c)
            continue
        try:
            if safe and _sanitize_segment(c.name, field_name="filename") == safe:
                matches.append(c)
        except DocumentAdminError:
            continue

    uniq = sorted({m.resolve() for m in matches}, key=lambda x: str(x))
    if len(uniq) == 1:
        return uniq[0]
    if not uniq:
        raise DocumentAdminError(f"File not found for delete: {hint}" if hint else "File not found")
    raise DocumentAdminError(f"Ambiguous filename: {filename!r}")


def _categories() -> List[str]:
    if not DOCS_DIR.is_dir():
        return []
    return sorted([p.name for p in DOCS_DIR.iterdir() if p.is_dir()])


def ensure_category(category: str) -> str:
    cat = _sanitize_segment(category, field_name="category")
    (DOCS_DIR / cat).mkdir(parents=True, exist_ok=True)
    return cat


def resolve_upload_category(category: Optional[str]) -> str:
    """Target folder under data/documents*. Empty → RAG_DEFAULT_CATEGORY (single corpus / catalog)."""
    raw = (category or "").strip()
    if raw:
        return ensure_category(raw)
    return ensure_category(settings.RAG_DEFAULT_CATEGORY)


def _active_source(category: str) -> str:
    md_dir = DOCS_MD_DIR / category
    txt_dir = DOCS_TXT_DIR / category
    if md_dir.is_dir() and any(md_dir.glob("*.md")):
        return "md"
    if txt_dir.is_dir() and any(txt_dir.glob("*.txt")):
        return "txt"
    return "docx"


def _list_files(category: str, source: str, *, username: str = "") -> List[dict]:
    files: List[dict] = []
    is_procedures = category == "procedures"
    user = (username or "").strip()

    def _with_logigramme(entry: dict, stem: str) -> dict:
        if is_procedures:
            entry["has_logigramme"] = logigramme_exists(category, stem)
            entry["has_logigramme_draft"] = (
                logigramme_draft_exists(category, stem, user) if user else False
            )
        return entry

    if source == "md":
        for p in sorted((DOCS_MD_DIR / category).glob("*.md")):
            text = _read_md(p)
            files.append(
                _with_logigramme(
                    {"name": p.name, "stem": p.stem, "source": "md", "chars": len(text)},
                    p.stem,
                )
            )
    elif source == "txt":
        for p in sorted((DOCS_TXT_DIR / category).glob("*.txt")):
            text = _read_txt(p)
            files.append(
                _with_logigramme(
                    {"name": p.name, "stem": p.stem, "source": "txt", "chars": len(text)},
                    p.stem,
                )
            )
    else:
        for p in sorted((DOCS_DIR / category).glob("*.docx")):
            md_path = DOCS_MD_DIR / category / f"{p.stem}.md"
            if md_path.exists():
                text = _read_md(md_path)
            else:
                text = _read_docx(p)
            files.append(
                _with_logigramme(
                    {
                        "name": p.name,
                        "stem": p.stem,
                        "source": "docx",
                        "chars": len(text),
                        "has_md_export": md_path.exists(),
                    },
                    p.stem,
                )
            )
    return files


def get_overview(*, username: str = "") -> dict:
    """List corpus folders and files. Category size is informational only (no admin cap)."""
    user = (username or "").strip()
    categories = []
    for cat in _categories():
        try:
            source = _active_source(cat)
            files = _list_files(cat, source, username=user)
            total_chars = sum(f["chars"] for f in files)
            categories.append(
                {
                    "name": cat,
                    "active_source": source,
                    "total_chars": total_chars,
                    "file_count": len(files),
                    "files": files,
                }
            )
        except Exception:
            logger.exception("documents_admin: skipped category %r in get_overview", cat)
            continue
    try:
        raw_default = (settings.RAG_DEFAULT_CATEGORY or "").strip() or "procedures"
        default_cat = _sanitize_segment(raw_default, field_name="RAG_DEFAULT_CATEGORY")
    except DocumentAdminError:
        logger.warning("RAG_DEFAULT_CATEGORY invalid %r; using procedures", settings.RAG_DEFAULT_CATEGORY)
        default_cat = "procedures"
    return {
        "categories": categories,
        "corpus": {
            "default_category": default_cat,
            "single_corpus": True,
            "hint": "Les dossiers (categories) servent d'étiquettes pour le modele; les fichiers ne sont plus bloques par un plafond de caracteres dans l'admin.",
        },
    }


def upload_document(
    category: Optional[str],
    filename: str,
    data: bytes,
) -> dict:
    cat = resolve_upload_category(category)
    safe_name = _sanitize_segment(filename, field_name="filename")
    ext = Path(safe_name).suffix.lower()
    stem = Path(safe_name).stem
    created: List[Path] = []
    try:
        if ext == ".txt":
            dst_dir = DOCS_TXT_DIR / cat
            dst_dir.mkdir(parents=True, exist_ok=True)
            dst = dst_dir / f"{stem}.txt"
            if dst.exists():
                raise DocumentAdminError(f"File already exists: {dst.name}")
            dst.write_bytes(data)
            created.append(dst)
        elif ext == ".docx":
            docx_dir = DOCS_DIR / cat
            md_dir = DOCS_MD_DIR / cat
            docx_dir.mkdir(parents=True, exist_ok=True)
            md_dir.mkdir(parents=True, exist_ok=True)
            dst = docx_dir / f"{stem}.docx"
            if dst.exists():
                raise DocumentAdminError(f"File already exists: {dst.name}")
            dst.write_bytes(data)
            created.append(dst)
            md_text = convert_docx_to_markdown(dst)
            if md_text:
                md_path = md_dir / f"{stem}.md"
                md_path.write_text(md_text, encoding="utf-8")
                created.append(md_path)
        elif ext == ".md":
            md_dir = DOCS_MD_DIR / cat
            md_dir.mkdir(parents=True, exist_ok=True)
            dst = md_dir / f"{stem}.md"
            if dst.exists():
                raise DocumentAdminError(f"File already exists: {dst.name}")
            dst.write_bytes(data)
            created.append(dst)
        else:
            raise DocumentAdminError("Only .docx, .txt, and .md are supported")

        return {"category": cat, "filename": f"{stem}{ext}"}
    except DocumentAdminError:
        for p in reversed(created):
            p.unlink(missing_ok=True)
        raise
    except Exception as exc:
        for p in reversed(created):
            p.unlink(missing_ok=True)
        raise DocumentAdminError(f"Impossible de traiter le fichier ({safe_name}): {exc}") from exc


def move_document(
    source_category: str,
    target_category: str,
    source_kind: str,
    filename: str,
) -> dict:
    src_cat = ensure_category(source_category)
    dst_cat = ensure_category(target_category)
    if src_cat == dst_cat:
        raise DocumentAdminError("Source and target categories are the same")
    kind = _sanitize_segment(source_kind, field_name="source").lower()

    moved_pairs: List[Tuple[Path, Path]] = []
    try:
        if kind == "txt":
            src = _resolve_file_under_dir(DOCS_TXT_DIR / src_cat, filename, hint=filename)
            dst_dir = DOCS_TXT_DIR / dst_cat
            dst_dir.mkdir(parents=True, exist_ok=True)
            dst = dst_dir / src.name
            if dst.exists():
                raise DocumentAdminError("Target file already exists")
            shutil.move(str(src), str(dst))
            moved_pairs.append((dst, src))
        elif kind == "docx":
            src = _resolve_file_under_dir(DOCS_DIR / src_cat, filename, hint=filename)
            dst_dir = DOCS_DIR / dst_cat
            dst_dir.mkdir(parents=True, exist_ok=True)
            dst = dst_dir / src.name
            if dst.exists():
                raise DocumentAdminError("Target file already exists")
            shutil.move(str(src), str(dst))
            moved_pairs.append((dst, src))
            src_md = DOCS_MD_DIR / src_cat / f"{src.stem}.md"
            if src_md.exists():
                dst_md_dir = DOCS_MD_DIR / dst_cat
                dst_md_dir.mkdir(parents=True, exist_ok=True)
                dst_md = dst_md_dir / src_md.name
                if dst_md.exists():
                    raise DocumentAdminError(f"Target md export already exists: {dst_md.name}")
                shutil.move(str(src_md), str(dst_md))
                moved_pairs.append((dst_md, src_md))
        elif kind == "md":
            src = _resolve_file_under_dir(DOCS_MD_DIR / src_cat, filename, hint=filename)
            dst_dir = DOCS_MD_DIR / dst_cat
            dst_dir.mkdir(parents=True, exist_ok=True)
            dst = dst_dir / src.name
            if dst.exists():
                raise DocumentAdminError("Target file already exists")
            shutil.move(str(src), str(dst))
            moved_pairs.append((dst, src))
            stem = src.stem
            src_docx = DOCS_DIR / src_cat / f"{stem}.docx"
            if src_docx.exists():
                dst_docx_dir = DOCS_DIR / dst_cat
                dst_docx_dir.mkdir(parents=True, exist_ok=True)
                dst_docx = dst_docx_dir / src_docx.name
                if dst_docx.exists():
                    raise DocumentAdminError(f"Target docx already exists: {dst_docx.name}")
                shutil.move(str(src_docx), str(dst_docx))
                moved_pairs.append((dst_docx, src_docx))
        else:
            raise DocumentAdminError("Unsupported source kind")

        return {"from": src_cat, "to": dst_cat, "filename": moved_pairs[0][1].name, "source": kind}
    except Exception:
        for dst, src in reversed(moved_pairs):
            if dst.exists() and not src.exists():
                src.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(dst), str(src))
        raise


def delete_document_category(category: str) -> dict:
    """Remove all .docx/.md/.txt for one corpus folder (empty dirs removed)."""
    cat = _sanitize_segment(category, field_name="category")
    removed = 0
    for folder, pattern in (
        (DOCS_DIR / cat, "*.docx"),
        (DOCS_MD_DIR / cat, "*.md"),
        (DOCS_TXT_DIR / cat, "*.txt"),
    ):
        if not folder.is_dir():
            continue
        for p in list(folder.glob(pattern)):
            try:
                p.unlink(missing_ok=True)
                removed += 1
            except OSError:
                pass
    # Drop empty category directories (optional cleanup)
    for folder in (DOCS_TXT_DIR / cat, DOCS_MD_DIR / cat, DOCS_DIR / cat):
        try:
            if folder.is_dir() and not any(folder.iterdir()):
                folder.rmdir()
        except OSError:
            pass
    return {"category": cat, "files_removed": removed}


def delete_document(category: str, source_kind: str, filename: str) -> dict:
    cat = ensure_category(category)
    kind = _sanitize_segment(source_kind, field_name="source").lower()

    if kind == "txt":
        path = _resolve_file_under_dir(DOCS_TXT_DIR / cat, filename, hint=filename)
        path.unlink()
    elif kind == "docx":
        path = _resolve_file_under_dir(DOCS_DIR / cat, filename, hint=filename)
        path.unlink()
        md_path = DOCS_MD_DIR / cat / f"{path.stem}.md"
        md_path.unlink(missing_ok=True)
    elif kind == "md":
        path = _resolve_file_under_dir(DOCS_MD_DIR / cat, filename, hint=filename)
        path.unlink()
        docx_path = DOCS_DIR / cat / f"{path.stem}.docx"
        docx_path.unlink(missing_ok=True)
    else:
        raise DocumentAdminError("Unsupported source kind")

    return {"deleted": True, "category": cat, "filename": path.name, "source": kind}


def _restore_deleted(
    file_bytes: bytes,
    category: str,
    source_kind: str,
    filename: str,
    md_bytes: Optional[bytes],
    *,
    docx_bytes: Optional[bytes] = None,
) -> None:
    cat = ensure_category(category)
    kind = _sanitize_segment(source_kind, field_name="source").lower()
    base_name = _reject_unsafe_basename(filename)
    if kind == "txt":
        path = DOCS_TXT_DIR / cat / base_name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(file_bytes)
    elif kind == "docx":
        path = DOCS_DIR / cat / base_name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(file_bytes)
        if md_bytes is not None:
            md = DOCS_MD_DIR / cat / f"{path.stem}.md"
            md.parent.mkdir(parents=True, exist_ok=True)
            md.write_bytes(md_bytes)
    elif kind == "md":
        md = DOCS_MD_DIR / cat / base_name
        md.parent.mkdir(parents=True, exist_ok=True)
        md.write_bytes(file_bytes)
        if docx_bytes is not None:
            docx = DOCS_DIR / cat / f"{md.stem}.docx"
            docx.parent.mkdir(parents=True, exist_ok=True)
            docx.write_bytes(docx_bytes)


def apply_plan(
    *,
    uploads: List[dict],
    moves: List[dict],
    deletes: List[dict],
    *,
    username: str = "",
) -> dict:
    """Apply staged document operations atomically (best-effort rollback)."""
    undo_stack: List[dict] = []
    try:
        for op in deletes:
            cat = ensure_category(op.get("category", ""))
            kind = _sanitize_segment(op.get("source_kind", ""), field_name="source").lower()
            filename_input = (op.get("filename") or "").strip()

            if kind == "txt":
                path = _resolve_file_under_dir(DOCS_TXT_DIR / cat, filename_input, hint=filename_input)
                file_bytes = path.read_bytes()
                delete_document(cat, kind, path.name)
                undo_stack.append(
                    {
                        "type": "restore_delete",
                        "category": cat,
                        "source_kind": kind,
                        "filename": path.name,
                        "file_bytes": file_bytes,
                        "md_bytes": None,
                    }
                )
            elif kind == "docx":
                path = _resolve_file_under_dir(DOCS_DIR / cat, filename_input, hint=filename_input)
                file_bytes = path.read_bytes()
                md_path = DOCS_MD_DIR / cat / f"{path.stem}.md"
                md_bytes = md_path.read_bytes() if md_path.exists() else None
                delete_document(cat, kind, path.name)
                undo_stack.append(
                    {
                        "type": "restore_delete",
                        "category": cat,
                        "source_kind": kind,
                        "filename": path.name,
                        "file_bytes": file_bytes,
                        "md_bytes": md_bytes,
                    }
                )
            elif kind == "md":
                path = _resolve_file_under_dir(DOCS_MD_DIR / cat, filename_input, hint=filename_input)
                file_bytes = path.read_bytes()
                docx_path = DOCS_DIR / cat / f"{path.stem}.docx"
                docx_bytes = docx_path.read_bytes() if docx_path.exists() else None
                delete_document(cat, kind, path.name)
                undo_stack.append(
                    {
                        "type": "restore_delete",
                        "category": cat,
                        "source_kind": kind,
                        "filename": path.name,
                        "file_bytes": file_bytes,
                        "md_bytes": None,
                        "docx_bytes": docx_bytes,
                    }
                )
            else:
                raise DocumentAdminError("Unsupported source kind")

        for op in moves:
            src = ensure_category(op.get("source_category", ""))
            dst = ensure_category(op.get("target_category", ""))
            kind = _sanitize_segment(op.get("source_kind", ""), field_name="source").lower()
            filename_input = (op.get("filename") or "").strip()
            moved = move_document(src, dst, kind, filename_input)
            undo_stack.append(
                {
                    "type": "reverse_move",
                    "source_category": dst,
                    "target_category": src,
                    "source_kind": kind,
                    "filename": moved["filename"],
                }
            )

        for op in uploads:
            cat = resolve_upload_category(op.get("category"))
            filename = op.get("filename", "")
            data = op.get("data", b"")
            if not isinstance(data, (bytes, bytearray)) or not data:
                raise DocumentAdminError(f"Upload payload missing for {filename}")
            out = upload_document(cat, filename, bytes(data))
            undo_stack.append(
                {
                    "type": "delete_upload",
                    "category": cat,
                    "source_kind": Path(out["filename"]).suffix.lower().lstrip("."),
                    "filename": out["filename"],
                }
            )

        return get_overview(username=username)
    except Exception:
        for step in reversed(undo_stack):
            try:
                if step["type"] == "restore_delete":
                    _restore_deleted(
                        file_bytes=step["file_bytes"],
                        category=step["category"],
                        source_kind=step["source_kind"],
                        filename=step["filename"],
                        md_bytes=step.get("md_bytes"),
                        docx_bytes=step.get("docx_bytes"),
                    )
                elif step["type"] == "reverse_move":
                    move_document(
                        step["source_category"],
                        step["target_category"],
                        step["source_kind"],
                        step["filename"],
                    )
                elif step["type"] == "delete_upload":
                    kind = (step["source_kind"] or "").lower()
                    if kind == "txt":
                        sk = "txt"
                    elif kind == "md":
                        sk = "md"
                    else:
                        sk = "docx"
                    delete_document(step["category"], sk, step["filename"])
            except Exception:
                pass
        raise
