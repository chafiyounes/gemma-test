#!/usr/bin/env python3
"""Export SOP ``.docx`` to Markdown for RAG (tables, headings, no images/headers).

Reads:   data/documents/<Category>/*.docx
Writes:  data/documents_md/<Category>/<same_stem>.md

The API loads ``data/documents_md/<cat>/*.md`` when present (see ``core/documents.py``).

Usage:
    python -m scripts.export_sop_to_md
    python -m scripts.export_sop_to_md --dry-run
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.documents import DOCS_DIR, DOCS_MD_DIR  # noqa: E402
from core.docx_to_md import export_category  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description="Export SOP docx → Markdown under data/documents_md/")
    ap.add_argument("--dry-run", action="store_true", help="Print actions only")
    args = ap.parse_args()

    if not DOCS_DIR.is_dir():
        print(f"Missing documents dir: {DOCS_DIR}", file=sys.stderr)
        sys.exit(1)

    n_out = 0
    for sub in sorted(DOCS_DIR.iterdir()):
        if not sub.is_dir():
            continue
        cat = sub.name
        if not list(sub.glob("*.docx")):
            continue
        out_dir = DOCS_MD_DIR / cat
        n_out += export_category(sub, out_dir, dry_run=args.dry_run)

    print(f"Done. {n_out} file(s). Output root: {DOCS_MD_DIR}")


if __name__ == "__main__":
    main()
