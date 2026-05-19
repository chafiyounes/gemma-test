#!/usr/bin/env python3
"""Find indexed docs matching a hint (run on pod)."""
import sys

from core.document_preview import _extract_title_from_text, _match_score, resolve_document
from core.documents import get_store

hint = " ".join(sys.argv[1:]) or "adresse email"
store = get_store()
print("resolve:", resolve_document(store, hint, "procedures"))
print("--- top matches ---")
hl = hint
rows = []
for cat, idx in store.indexes.items():
    for d in idx.docs:
        title = _extract_title_from_text(d.text)
        score = _match_score(hl, d.name, title)
        if score >= 0.25:
            rows.append((score, cat, d.name, title[:80]))
rows.sort(reverse=True)
for score, cat, name, title in rows[:12]:
    print(f"{score:.2f}\t{cat}\t{name}\t| {title}")
