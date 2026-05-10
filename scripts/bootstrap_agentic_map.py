#!/usr/bin/env python3
"""Build ``data/agentic_map/<category>.json`` from DocStore.

Default: heuristic titles/tags (no API).

  python scripts/bootstrap_agentic_map.py

Design-spec map rows via vLLM (same machine as API or tunneled port):

  python scripts/bootstrap_agentic_map.py --llm

Then build embedding indices (GPU recommended):

  python scripts/build_agentic_embedding_index.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app_config.settings import settings  # noqa: E402
from core.agentic_map_llm import extract_map_entry_llm  # noqa: E402
from core.documents import _tokenize, get_store  # noqa: E402

_KEYWORD_CAT: list[tuple[str, str]] = [
    ("facturation", "facturation"),
    ("facture", "facturation"),
    ("comptabilité", "facturation"),
    ("sécurité", "sécurité"),
    ("mot de passe", "sécurité"),
    ("compte", "compte"),
    ("accès", "accès"),
    ("connexion", "accès"),
    ("technique", "technique"),
    ("api", "technique"),
    ("plateforme", "technique"),
]


def _guess_category(title: str, text_sample: str) -> str:
    low = f"{title} {text_sample[:800]}".lower()
    for kw, cat in _KEYWORD_CAT:
        if kw in low:
            return cat
    return "autre"


def _title_from_doc(name: str, text: str) -> str:
    import re

    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        s = re.sub(r"^#+\s*", "", s)
        s = re.sub(r"\*+", "", s).strip()
        if len(s) < 3:
            continue
        words = s.split()[:8]
        return " ".join(words)
    return name.replace("_", " ")[:80]


def _tags_from(text: str, title: str, *, max_tags: int = 6) -> list[str]:
    blob = f"{title} {text[:500]}"
    toks = [t for t in _tokenize(blob) if len(t) > 2][:24]
    out: list[str] = []
    for t in toks:
        if t not in out:
            out.append(t)
        if len(out) >= max_tags:
            break
    return out


def run_heuristic(categories: list[str] | None) -> None:
    store = get_store()
    out_dir = Path(settings.AGENTIC_RAG_MAP_DIR)
    if not out_dir.is_absolute():
        out_dir = REPO_ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    if not store.indexes:
        print("DocStore has no categories; check data/documents_md or data/documents")
        sys.exit(1)

    pairs = sorted(store.indexes.items(), key=lambda x: x[0])
    if categories:
        want = set(categories)
        pairs = [(n, i) for n, i in pairs if n in want]
        for c in want:
            if c not in store.indexes:
                print(f"Unknown category skipped: {c}", file=sys.stderr)
        if not pairs:
            print("No matching categories.")
            sys.exit(1)

    for cat_name, idx in pairs:
        rows: list[dict] = []
        for d in idx.docs:
            title = _title_from_doc(d.name, d.text)
            tags = _tags_from(d.text, title)
            proc_cat = _guess_category(title, d.text)
            rows.append(
                {
                    "id": d.name,
                    "title": title,
                    "tags": tags,
                    "category": proc_cat,
                }
            )
        path = out_dir / f"{cat_name}.json"
        path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Wrote {path} ({len(rows)} entries)")


def run_llm(base_url: str, categories: list[str] | None) -> None:
    store = get_store()
    out_dir = Path(settings.AGENTIC_RAG_MAP_DIR)
    if not out_dir.is_absolute():
        out_dir = REPO_ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    if not store.indexes:
        print("DocStore has no categories")
        sys.exit(1)

    targets = sorted(store.indexes.keys())
    if categories:
        targets = [c for c in categories if c in store.indexes]
        unknown = set(categories) - set(store.indexes.keys())
        for u in unknown:
            print(f"Unknown category skipped: {u}", file=sys.stderr)
    if not targets:
        print("No categories to process.")
        sys.exit(1)

    api_key = settings.VLLM_API_KEY or "no-key"
    headers = {"Authorization": f"Bearer {api_key}"}
    with httpx.Client(base_url=base_url.rstrip("/"), headers=headers, timeout=300.0) as client:
        try:
            r = client.get("/health", timeout=15.0)
            if r.status_code != 200:
                print(f"vLLM /health returned {r.status_code}", file=sys.stderr)
        except Exception as exc:
            print(f"vLLM unreachable at {base_url}: {exc}", file=sys.stderr)
            sys.exit(1)

        for cat_name in targets:
            idx = store.indexes[cat_name]
            rows: list[dict] = []
            for i, d in enumerate(idx.docs):
                print(f"[{cat_name}] LLM map {i + 1}/{len(idx.docs)} {d.name!r} …", flush=True)
                try:
                    row = extract_map_entry_llm(
                        document_id=d.name,
                        document_text=d.text,
                        client=client,
                    )
                    rows.append(row)
                except Exception as exc:
                    print(f"  FAILED {d.name}: {exc} — heuristic fallback", file=sys.stderr)
                    title = _title_from_doc(d.name, d.text)
                    rows.append(
                        {
                            "id": d.name,
                            "title": title,
                            "tags": _tags_from(d.text, title),
                            "category": _guess_category(title, d.text),
                        }
                    )
            path = out_dir / f"{cat_name}.json"
            path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"Wrote {path} ({len(rows)} entries)")


def main() -> None:
    ap = argparse.ArgumentParser(description="Build agentic map JSON per category")
    ap.add_argument(
        "--llm",
        action="store_true",
        help="Call vLLM for each document (design-spec map row)",
    )
    ap.add_argument(
        "--vllm-url",
        default=None,
        help="Override VLLM_BASE_URL (default from .env)",
    )
    ap.add_argument(
        "categories",
        nargs="*",
        help="Limit to these category names (default: all)",
    )
    args = ap.parse_args()
    if args.llm:
        url = args.vllm_url or settings.VLLM_BASE_URL
        run_llm(url, args.categories or None)
    else:
        run_heuristic(args.categories or None)


if __name__ == "__main__":
    main()
