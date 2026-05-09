#!/usr/bin/env python3
"""Heuristic agentic map bootstrap (no LLM). Writes data/agentic_map/<category>.json.

For LLM-generated map entries per the full spec, replace this with a worker that
calls the small model and upserts into Qdrant/e5; this script is enough to test
search_map + fetch_procedure + /chat?agentic_rag locally.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app_config.settings import settings  # noqa: E402
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


def main() -> None:
    store = get_store()
    out_dir = Path(settings.AGENTIC_RAG_MAP_DIR)
    if not out_dir.is_absolute():
        out_dir = REPO_ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    if not store.indexes:
        print("DocStore has no categories; check data/documents_md or data/documents")
        sys.exit(1)

    for cat_name, idx in sorted(store.indexes.items(), key=lambda x: x[0]):
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


if __name__ == "__main__":
    main()
