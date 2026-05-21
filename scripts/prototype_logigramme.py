#!/usr/bin/env python3
"""Prototype: generate a Mermaid logigramme from a procedure via direct vLLM call."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import httpx

from app_config.settings import settings
from core.documents import get_store
from core.logigramme_llm import (
    generate_logigramme_mermaid,
    validate_mermaid,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a Mermaid logigramme from a procedure.")
    parser.add_argument("--stem", required=True, help="Document stem (without extension)")
    parser.add_argument("--category", default="procedures", help="Document category folder")
    parser.add_argument(
        "--output",
        default=None,
        help="Output .mmd path (default: outputs/logigrammes/<stem>.mmd)",
    )
    parser.add_argument("--model", default=None, help="Override vLLM model name")
    args = parser.parse_args()

    store = get_store()
    text = store.get_document_by_stem(args.category, args.stem)
    if not text:
        print(f"ERROR: document not found: {args.category}/{args.stem}", file=sys.stderr)
        return 1

    base_url = settings.VLLM_BASE_URL.rstrip("/")
    print(f"vLLM: {base_url}")
    print(f"Document: {args.category}/{args.stem} ({len(text)} chars)")

    with httpx.Client(base_url=base_url, timeout=120.0) as client:
        mermaid = generate_logigramme_mermaid(
            document_text=text,
            client=client,
            model=args.model,
        )

    valid = validate_mermaid(mermaid)
    out_path = Path(args.output) if args.output else ROOT / "outputs" / "logigrammes" / f"{args.stem}.mmd"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(mermaid + "\n", encoding="utf-8")

    print(f"Valid Mermaid: {valid}")
    print(f"Lines: {len(mermaid.splitlines())}")
    print(f"Saved: {out_path}")
    print("--- preview ---")
    print(mermaid[:1200])
    if len(mermaid) > 1200:
        print("...")
    return 0 if valid else 2


if __name__ == "__main__":
    raise SystemExit(main())
