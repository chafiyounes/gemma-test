#!/usr/bin/env python3
"""Compare file counts on disk vs DocStore index (run from repo root, e.g. on the pod).

``data/documents_md`` and ``data/documents_txt`` are gitignored — they are never in
``git pull``/``reset``. This script helps see whether fewer indexed docs are due to
missing files, or to ingest rules (empty file, no indexable tokens).

Usage:
  python scripts/corpus_disk_vs_store.py
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.documents import DOCS_DIR, DOCS_MD_DIR, DOCS_TXT_DIR, get_store  # noqa: E402


def _disk_md_for_cat(cat: str) -> list[Path]:
    d = DOCS_MD_DIR / cat
    return sorted(d.rglob("*.md")) if d.is_dir() else []


def _disk_txt_for_cat(cat: str) -> list[Path]:
    d = DOCS_TXT_DIR / cat
    return sorted(d.rglob("*.txt")) if d.is_dir() else []


def main() -> int:
    store = get_store()
    cats = sorted(
        p.name for p in DOCS_DIR.iterdir() if p.is_dir()
    ) if DOCS_DIR.is_dir() else []

    print("=== Corpus: disk vs DocStore ===")
    print(f"REPO_ROOT={REPO_ROOT}")
    print()

    for cat in cats:
        md_n = len(_disk_md_for_cat(cat))
        txt_n = len(_disk_txt_for_cat(cat))
        src = "—"
        if md_n:
            src = f"documents_md ({md_n} .md paths)"
        elif txt_n:
            src = f"documents_txt ({txt_n} .txt paths)"

        idx_n = len(store.indexes[cat].docs) if cat in store.indexes else 0
        indexed = "yes" if cat in store.indexes else "no"

        print(f"[{cat}]")
        print(f"  on disk:   md_paths={md_n}  txt_paths={txt_n}  → loader would use: {src}")
        print(f"  indexed:   {idx_n} docs  ({indexed})")
        if (md_n or txt_n) and idx_n < max(md_n, txt_n):
            print(
                "  note: indexed < disk paths → some files skipped (empty, unreadable, or no indexable tokens)."
            )
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
