#!/usr/bin/env python3
"""Check whether local SOP files likely contain an answer theme (keyword audit).

Run on the same machine as the API / pod, from the repo root, so
``data/documents/<category>`` (or ``documents_txt``) are visible.

Examples:
  python scripts/rag_audit.py \\
    "Vendor bghay ybdel numéro de téléphone dyal client dyalo walakin colis déjà f livraison" \\
    procedures

Exit code 0 always; inspect printed table. If **no theme hits** in any file,
"absent des documents" may be justified. If hits exist, retrieval or prompting
should surface them — use admin RAG preview or raise ``RAG_INJECT_MAX_CHARS``.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app_config.settings import settings  # noqa: E402
from core.chat_policy import detect_lang_bucket, retrieval_anchor_query  # noqa: E402
from core.documents import expand_query_for_retrieval_fr_darija, get_store  # noqa: E402

THEMES: tuple[tuple[str, str], ...] = (
    ("téléphone / numéro / contact", r"téléphone|telephone|numéro|numero|portable|gsm|coordonn"),
    ("livraison / tournée", r"livraison|livrer|tournée|tournee|livreur|distribu|en cours"),
    ("modification données client", r"modif|changement|mise à jour|mise a jour|réexpéd|réexped"),
    ("colis / envoi", r"colis|envoi|expédition|expedition"),
    ("vendeur / expéditeur", r"vendeur|expéditeur|expediteur|boutique"),
)


def _count_pattern(text: str, pat: str) -> int:
    return len(re.findall(pat, text, flags=re.IGNORECASE))


def main() -> None:
    parser = argparse.ArgumentParser(description="Keyword/theme audit for RAG corpus.")
    parser.add_argument("question", help="User question (darija / fr / mix ok)")
    parser.add_argument(
        "category",
        nargs="?",
        default="",
        help="Subfolder under data/documents/ (default: from settings or first available)",
    )
    args = parser.parse_args()
    q = args.question.strip()
    store = get_store()
    cats = sorted(store.indexes.keys())
    if not cats:
        print("No document categories loaded. Add folders under data/documents/<name>/ with .txt or .docx.")
        return
    category = args.category.strip()
    if not category:
        d = (settings.RAG_DEFAULT_CATEGORY or "").strip()
        category = d if d in store.indexes else cats[0]
    if category not in store.indexes:
        print(f"Unknown category {category!r}. Available: {', '.join(cats)}")
        return

    bucket = detect_lang_bucket(q)
    rq = retrieval_anchor_query(q, [])
    expand = bucket in ("fr", "darija", "en")
    expanded = expand_query_for_retrieval_fr_darija(rq) if expand else rq
    top = store.retrieve(
        rq,
        category=category,
        k=max(settings.RAG_BM25_K, len(store.indexes[category].docs)),
        expand_fr_darija_hints=expand,
    )

    print("=== RAG audit ===")
    print(f"Category     : {category}")
    print(f"Lang bucket  : {bucket}")
    print(f"Raw anchor   : {rq[:200]}{'…' if len(rq) > 200 else ''}")
    print(f"Expanded Q   : {expanded[:260]}{'…' if len(expanded) > 260 else ''}")
    print()

    idx = store.indexes[category]
    print(f"Documents in category ({len(idx.docs)}):")
    print("-" * 100)
    any_hits = False
    for d in idx.docs:
        line_parts = [f"{d.name[:48]:<50}"]
        for label, pat in THEMES:
            n = _count_pattern(d.text, pat)
            line_parts.append(f"{label.split()[0][:6]}:{n}")
            if n:
                any_hits = True
        print("  ".join(line_parts))
    print("-" * 100)
    print("Theme legend:", ", ".join(t[0] for t in THEMES))
    print()

    print("BM25 order (retrieval):")
    for i, d in enumerate(top, 1):
        print(f"  {i:2}. {d.name}")
    print()

    ctx = store.build_all_docs_context(
        category=category,
        max_chars=settings.RAG_INJECT_MAX_CHARS,
        query=rq,
        expand_for_retrieval=expand,
        condense=settings.RAG_CONDENSE_DOCUMENTS,
    )
    n_docs_in_ctx = ctx.count("### Document :") if ctx else 0
    print(f"Simulated inject: {len(ctx)} chars, ~{n_docs_in_ctx} document header(s) in prompt block")
    if ctx:
        print("\n--- Start of injected text (800 chars) ---")
        print(ctx[:800])
        print("--- end ---")

    print()
    if not any_hits:
        print(
            "Verdict: **no keyword/theme hits** in this category for the listed themes.\n"
            "If your SOPs truly omit téléphone + livraison + modification, the model may be correct to say absent.\n"
            "Otherwise add or re-export text under data/documents_txt/."
        )
    else:
        print(
            "Verdict: **at least one theme appears** in some file(s).\n"
            "If the chat still says « absent », check: inject truncation (admin RAG preview), vLLM prompt length, or model refusal — not missing files."
        )


if __name__ == "__main__":
    main()
