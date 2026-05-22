"""Sidecar storage for procedure logigrammes (Mermaid)."""

from __future__ import annotations

from pathlib import Path

from core.mermaid_validate import normalize_mermaid, strip_code_fence, validate_mermaid

LOGIGRAMMES_DIR = Path(__file__).resolve().parents[1] / "data" / "logigrammes"
PROCEDURES_CATEGORY = "procedures"


class LogigrammeStoreError(Exception):
    pass


def path_for(category: str, stem: str) -> Path:
    cat = (category or "").strip()
    st = (stem or "").strip()
    if not cat or not st:
        raise LogigrammeStoreError("category and stem are required")
    if ".." in cat or ".." in st or "/" in cat or "\\" in cat:
        raise LogigrammeStoreError("invalid category or stem")
    return LOGIGRAMMES_DIR / cat / f"{st}.mmd"


def draft_path_for(category: str, stem: str) -> Path:
    cat = (category or "").strip()
    st = (stem or "").strip()
    if not cat or not st:
        raise LogigrammeStoreError("category and stem are required")
    if ".." in cat or ".." in st or "/" in cat or "\\" in cat:
        raise LogigrammeStoreError("invalid category or stem")
    return LOGIGRAMMES_DIR / cat / f"{st}.draft.mmd"


def exists(category: str, stem: str) -> bool:
    try:
        return path_for(category, stem).is_file()
    except LogigrammeStoreError:
        return False


def draft_exists(category: str, stem: str) -> bool:
    try:
        return draft_path_for(category, stem).is_file()
    except LogigrammeStoreError:
        return False


def read(category: str, stem: str) -> str | None:
    p = path_for(category, stem)
    if not p.is_file():
        return None
    return p.read_text(encoding="utf-8").strip()


def read_draft(category: str, stem: str) -> str | None:
    p = draft_path_for(category, stem)
    if not p.is_file():
        return None
    return p.read_text(encoding="utf-8").strip()


def save(category: str, stem: str, mermaid: str) -> Path:
    if category != PROCEDURES_CATEGORY:
        raise LogigrammeStoreError(f"logigrammes only allowed for category {PROCEDURES_CATEGORY!r}")
    cleaned = normalize_mermaid(mermaid or "")
    if not validate_mermaid(cleaned):
        raise LogigrammeStoreError("invalid Mermaid syntax")
    p = path_for(category, stem)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(cleaned + "\n", encoding="utf-8")
    delete_draft(category, stem)
    return p


def save_draft(category: str, stem: str, mermaid: str) -> Path:
    """Persist work-in-progress; not merged into RAG until published."""
    if category != PROCEDURES_CATEGORY:
        raise LogigrammeStoreError(f"logigrammes only allowed for category {PROCEDURES_CATEGORY!r}")
    cleaned = strip_code_fence((mermaid or "").strip())
    if not cleaned:
        raise LogigrammeStoreError("draft is empty")
    p = draft_path_for(category, stem)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(cleaned + "\n", encoding="utf-8")
    return p


def delete_draft(category: str, stem: str) -> bool:
    if category != PROCEDURES_CATEGORY:
        raise LogigrammeStoreError(f"logigrammes only allowed for category {PROCEDURES_CATEGORY!r}")
    p = draft_path_for(category, stem)
    if not p.is_file():
        return False
    p.unlink()
    return True


def delete(category: str, stem: str) -> bool:
    if category != PROCEDURES_CATEGORY:
        raise LogigrammeStoreError(f"logigrammes only allowed for category {PROCEDURES_CATEGORY!r}")
    p = path_for(category, stem)
    deleted = False
    if p.is_file():
        p.unlink()
        deleted = True
    if delete_draft(category, stem):
        deleted = True
    return deleted


def append_to_document_text(category: str, stem: str, text: str) -> str:
    """Merge published logigramme sidecar into indexed document body when present."""
    mermaid = read(category, stem)
    if not mermaid:
        return text
    block = f"\n\n## Logigramme (flowchart)\n```mermaid\n{mermaid}\n```\n"
    return (text or "").rstrip() + block
