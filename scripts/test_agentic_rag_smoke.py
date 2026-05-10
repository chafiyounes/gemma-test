#!/usr/bin/env python3
"""Offline smoke: load map, search_map (BM25), fetch_procedure. No vLLM."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app_config.settings import settings  # noqa: E402
from core.agentic_rag import fetch_procedure, load_map_entries, map_json_path, search_map  # noqa: E402
from core.documents import get_store  # noqa: E402


def main() -> int:
    store = get_store()
    cat = (sys.argv[1] if len(sys.argv) > 1 else settings.RAG_DEFAULT_CATEGORY).strip()
    if cat not in store.indexes:
        names = ", ".join(sorted(store.indexes.keys())) or "(none)"
        print(f"Unknown category {cat!r}. Known: {names}")
        return 1

    path = map_json_path(cat)
    entries = load_map_entries(cat)
    if not entries:
        print(f"No map at {path}. Run: python scripts/bootstrap_agentic_map.py")
        return 1

    q = sys.argv[2] if len(sys.argv) > 2 else "procédure livraison colis"
    hits = search_map(store, q, entries, category=cat, k=5)
    print("query:", q)
    print("hits:", json_dumps(hits))

    top_id = hits[0]["id"]
    body = fetch_procedure(store, cat, top_id)
    if body == "DOCUMENT_NOT_FOUND":
        print("fetch failed for", top_id)
        return 1
    print("fetch ok:", top_id, "chars=", len(body))
    return 0


def json_dumps(obj: object) -> str:
    import json

    return json.dumps(obj, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    raise SystemExit(main())
