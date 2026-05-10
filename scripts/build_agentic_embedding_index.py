#!/usr/bin/env python3
"""Build per-category NPZ indices for agentic map search (multilingual-e5-large).

Run after ``bootstrap_agentic_map.py`` (with or without ``--llm``):

  python scripts/build_agentic_embedding_index.py
  python scripts/build_agentic_embedding_index.py procedures temp

Requires: pip install sentence-transformers
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app_config.settings import settings  # noqa: E402
from core.agentic_embeddings import (  # noqa: E402
    embed_passages,
    get_sentence_transformer,
    index_path_for_category,
)
from core.agentic_rag import load_map_entries  # noqa: E402
from core.documents import get_store  # noqa: E402


def main() -> int:
    store = get_store()
    if get_sentence_transformer() is None:
        print(
            "sentence-transformers not available or model failed to load. "
            "pip install sentence-transformers",
            file=sys.stderr,
        )
        return 1

    cats = [sys.argv[i] for i in range(1, len(sys.argv)) if not sys.argv[i].startswith("-")]
    if not cats:
        cats = sorted(store.indexes.keys())

    for cat in cats:
        if cat not in store.indexes:
            print(f"skip unknown category: {cat}", file=sys.stderr)
            continue
        entries = load_map_entries(cat)
        if not entries:
            print(f"skip {cat}: no map JSON — run bootstrap_agentic_map.py", file=sys.stderr)
            continue
        lines = [f"{e.title} {' '.join(e.tags)}" for e in entries]
        emb = embed_passages(lines)
        if emb is None:
            print(f"failed to embed category {cat}", file=sys.stderr)
            return 1
        path = index_path_for_category(cat)
        ids = np.array([e.id for e in entries], dtype=object)
        np.savez_compressed(path, emb=emb.astype(np.float32), ids=ids)
        print(f"Wrote {path} shape={emb.shape}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
