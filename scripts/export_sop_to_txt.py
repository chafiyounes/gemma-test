#!/usr/bin/env python3
"""Export SOP .docx files to cleaned .txt (Markdown-shaped content from DOCX).

Prefer ``python -m scripts.export_sop_to_md`` for ``data/documents_md`` (API default).
This script still writes ``.txt`` for legacy workflows.

Usage:
    python -m scripts.export_sop_to_txt
    python -m scripts.export_sop_to_txt --dry-run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Project root
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.documents import DOCS_DIR, DOCS_TXT_DIR  # noqa: E402
from core.docx_to_md import convert_docx_to_markdown  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description="Export cleaned SOP docx → txt")
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
        out_dir = DOCS_TXT_DIR / cat
        for docx in sorted(sub.glob("*.docx")):
            text = convert_docx_to_markdown(docx)
            if not text.strip():
                print(f"skip empty: {docx}")
                continue
            out_path = out_dir / f"{docx.stem}.txt"
            if args.dry_run:
                print(f"would write {out_path} ({len(text)} chars)")
            else:
                out_dir.mkdir(parents=True, exist_ok=True)
                out_path.write_text(text, encoding="utf-8")
                print(f"wrote {out_path}")
            n_out += 1

    print(f"Done. {n_out} file(s). Output root: {DOCS_TXT_DIR}")


if __name__ == "__main__":
    main()
