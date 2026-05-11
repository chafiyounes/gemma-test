from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from app_config.settings import settings
from core.documents import DOCS_DIR, DOCS_MD_DIR, DOCS_TXT_DIR, _read_docx, _read_md, _read_txt
from core.docx_to_md import convert_docx_to_markdown

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


def _list_files(category: str, source: str) -> List[dict]:
    files: List[dict] = []
    if source == "md":
        for p in sorted((DOCS_MD_DIR / category).glob("*.md")):
            text = _read_md(p)
            files.append({"name": p.name, "stem": p.stem, "source": "md", "chars": len(text)})
    elif source == "txt":
        for p in sorted((DOCS_TXT_DIR / category).glob("*.txt")):
            text = _read_txt(p)
            files.append({"name": p.name, "stem": p.stem, "source": "txt", "chars": len(text)})
    else:
        for p in sorted((DOCS_DIR / category).glob("*.docx")):
            md_path = DOCS_MD_DIR / category / f"{p.stem}.md"
            if md_path.exists():
                text = _read_md(md_path)
            else:
                text = _read_docx(p)
            files.append(
                {
                    "name": p.name,
                    "stem": p.stem,
                    "source": "docx",
                    "chars": len(text),
                    "has_md_export": md_path.exists(),
                }
            )
    return files


def _budget() -> Dict[str, int]:
    reserve = max(0, int(settings.RAG_CHAT_HISTORY_RESERVE_CHARS))
    inject_cap = max(0, int(settings.RAG_INJECT_MAX_CHARS))
    category_limit = max(1, inject_cap - reserve)
    return {
        "inject_cap_chars": inject_cap,
        "history_reserve_chars": reserve,
        "category_limit_chars": category_limit,
    }


def get_overview() -> dict:
    budget = _budget()
    categories = []
    for cat in _categories():
        source = _active_source(cat)
        files = _list_files(cat, source)
        total_chars = sum(f["chars"] for f in files)
        overflow = total_chars > budget["category_limit_chars"]
        categories.append(
            {
                "name": cat,
                "active_source": source,
                "total_chars": total_chars,
                "remaining_chars": budget["category_limit_chars"] - total_chars,
                "overflow": overflow,
                "file_count": len(files),
                "files": files,
            }
        )
    default_cat = _sanitize_segment(
        settings.RAG_DEFAULT_CATEGORY, field_name="RAG_DEFAULT_CATEGORY"
    )
    return {
        "budget": budget,
        "categories": categories,
        "corpus": {
            "default_category": default_cat,
            "single_corpus": True,
            "hint": "Uploads sans categorie vont dans default_category (alignez RAG_DEFAULT_CATEGORY dans .env avec le filtre /chat).",
        },
    }


def _category_overflow(category: str) -> Tuple[bool, int]:
    overview = get_overview()
    limit = overview["budget"]["category_limit_chars"]
    for cat in overview["categories"]:
        if cat["name"] == category:
            return cat["total_chars"] > limit, cat["total_chars"]
    return False, 0


def _assert_no_overflow(category: str) -> None:
    overflow, total = _category_overflow(category)
    if overflow:
        limit = _budget()["category_limit_chars"]
        raise DocumentAdminError(
            f"Category '{category}' exceeds context budget ({total} > {limit} chars). "
            "Move/delete files before saving."
        )


def upload_document(
    category: Optional[str],
    filename: str,
    data: bytes,
    *,
    enforce_overflow: bool = True,
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
        else:
            raise DocumentAdminError("Only .docx and .txt are supported")

        if enforce_overflow:
            _assert_no_overflow(cat)
        return {"category": cat, "filename": f"{stem}{ext}"}
    except Exception:
        for p in reversed(created):
            p.unlink(missing_ok=True)
        raise


def move_document(
    source_category: str,
    target_category: str,
    source_kind: str,
    filename: str,
    *,
    enforce_overflow: bool = True,
) -> dict:
    src_cat = ensure_category(source_category)
    dst_cat = ensure_category(target_category)
    if src_cat == dst_cat:
        raise DocumentAdminError("Source and target categories are the same")
    kind = _sanitize_segment(source_kind, field_name="source").lower()
    safe_name = _sanitize_segment(filename, field_name="filename")

    moved_pairs: List[Tuple[Path, Path]] = []
    try:
        if kind == "txt":
            src = DOCS_TXT_DIR / src_cat / safe_name
            dst_dir = DOCS_TXT_DIR / dst_cat
            dst_dir.mkdir(parents=True, exist_ok=True)
            dst = dst_dir / safe_name
            if not src.exists():
                raise DocumentAdminError("Source file not found")
            if dst.exists():
                raise DocumentAdminError("Target file already exists")
            shutil.move(str(src), str(dst))
            moved_pairs.append((dst, src))
        elif kind == "docx":
            src = DOCS_DIR / src_cat / safe_name
            dst_dir = DOCS_DIR / dst_cat
            dst_dir.mkdir(parents=True, exist_ok=True)
            dst = dst_dir / safe_name
            if not src.exists():
                raise DocumentAdminError("Source file not found")
            if dst.exists():
                raise DocumentAdminError("Target file already exists")
            shutil.move(str(src), str(dst))
            moved_pairs.append((dst, src))
            src_md = DOCS_MD_DIR / src_cat / f"{Path(safe_name).stem}.md"
            if src_md.exists():
                dst_md_dir = DOCS_MD_DIR / dst_cat
                dst_md_dir.mkdir(parents=True, exist_ok=True)
                dst_md = dst_md_dir / src_md.name
                if dst_md.exists():
                    raise DocumentAdminError(f"Target md export already exists: {dst_md.name}")
                shutil.move(str(src_md), str(dst_md))
                moved_pairs.append((dst_md, src_md))
        else:
            raise DocumentAdminError("Unsupported source kind")

        if enforce_overflow:
            _assert_no_overflow(dst_cat)
        return {"from": src_cat, "to": dst_cat, "filename": safe_name, "source": kind}
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
    safe_name = _sanitize_segment(filename, field_name="filename")

    if kind == "txt":
        path = DOCS_TXT_DIR / cat / safe_name
        if not path.exists():
            raise DocumentAdminError("File not found")
        path.unlink()
    elif kind == "docx":
        path = DOCS_DIR / cat / safe_name
        if not path.exists():
            raise DocumentAdminError("File not found")
        path.unlink()
        md_path = DOCS_MD_DIR / cat / f"{Path(safe_name).stem}.md"
        md_path.unlink(missing_ok=True)
    else:
        raise DocumentAdminError("Unsupported source kind")

    return {"deleted": True, "category": cat, "filename": safe_name, "source": kind}


def _restore_deleted(file_bytes: bytes, category: str, source_kind: str, filename: str, md_bytes: Optional[bytes]) -> None:
    cat = ensure_category(category)
    kind = _sanitize_segment(source_kind, field_name="source").lower()
    safe_name = _sanitize_segment(filename, field_name="filename")
    if kind == "txt":
        path = DOCS_TXT_DIR / cat / safe_name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(file_bytes)
    elif kind == "docx":
        path = DOCS_DIR / cat / safe_name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(file_bytes)
        if md_bytes is not None:
            md = DOCS_MD_DIR / cat / f"{Path(safe_name).stem}.md"
            md.parent.mkdir(parents=True, exist_ok=True)
            md.write_bytes(md_bytes)


def apply_plan(
    *,
    uploads: List[dict],
    moves: List[dict],
    deletes: List[dict],
) -> dict:
    """Apply staged document operations atomically (best-effort rollback)."""
    undo_stack: List[dict] = []
    try:
        for op in deletes:
            cat = ensure_category(op.get("category", ""))
            kind = _sanitize_segment(op.get("source_kind", ""), field_name="source").lower()
            filename = _sanitize_segment(op.get("filename", ""), field_name="filename")

            if kind == "txt":
                path = DOCS_TXT_DIR / cat / filename
                if not path.exists():
                    raise DocumentAdminError(f"File not found for delete: {filename}")
                file_bytes = path.read_bytes()
                delete_document(cat, kind, filename)
                undo_stack.append(
                    {
                        "type": "restore_delete",
                        "category": cat,
                        "source_kind": kind,
                        "filename": filename,
                        "file_bytes": file_bytes,
                        "md_bytes": None,
                    }
                )
            elif kind == "docx":
                path = DOCS_DIR / cat / filename
                if not path.exists():
                    raise DocumentAdminError(f"File not found for delete: {filename}")
                file_bytes = path.read_bytes()
                md_path = DOCS_MD_DIR / cat / f"{Path(filename).stem}.md"
                md_bytes = md_path.read_bytes() if md_path.exists() else None
                delete_document(cat, kind, filename)
                undo_stack.append(
                    {
                        "type": "restore_delete",
                        "category": cat,
                        "source_kind": kind,
                        "filename": filename,
                        "file_bytes": file_bytes,
                        "md_bytes": md_bytes,
                    }
                )
            else:
                raise DocumentAdminError("Unsupported source kind")

        for op in moves:
            src = ensure_category(op.get("source_category", ""))
            dst = ensure_category(op.get("target_category", ""))
            kind = _sanitize_segment(op.get("source_kind", ""), field_name="source").lower()
            filename = _sanitize_segment(op.get("filename", ""), field_name="filename")
            move_document(src, dst, kind, filename, enforce_overflow=False)
            undo_stack.append(
                {
                    "type": "reverse_move",
                    "source_category": dst,
                    "target_category": src,
                    "source_kind": kind,
                    "filename": filename,
                }
            )

        for op in uploads:
            cat = resolve_upload_category(op.get("category"))
            filename = op.get("filename", "")
            data = op.get("data", b"")
            if not isinstance(data, (bytes, bytearray)) or not data:
                raise DocumentAdminError(f"Upload payload missing for {filename}")
            out = upload_document(cat, filename, bytes(data), enforce_overflow=False)
            undo_stack.append(
                {
                    "type": "delete_upload",
                    "category": cat,
                    "source_kind": Path(out["filename"]).suffix.lower().lstrip("."),
                    "filename": out["filename"],
                }
            )

        overview = get_overview()
        limit = overview["budget"]["category_limit_chars"]
        offenders = [c for c in overview["categories"] if c["overflow"]]
        if offenders:
            detail = ", ".join(f"{c['name']} ({c['total_chars']}/{limit})" for c in offenders)
            raise DocumentAdminError(f"Context budget exceeded after save: {detail}")
        return overview
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
                    )
                elif step["type"] == "reverse_move":
                    move_document(
                        step["source_category"],
                        step["target_category"],
                        step["source_kind"],
                        step["filename"],
                        enforce_overflow=False,
                    )
                elif step["type"] == "delete_upload":
                    kind = step["source_kind"]
                    source_kind = "txt" if kind == "txt" else "docx"
                    delete_document(step["category"], source_kind, step["filename"])
            except Exception:
                pass
        raise
