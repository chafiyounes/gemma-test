#!/usr/bin/env python3
"""Evaluate classic BM25 RAG on composite questions spanning 3+ procedure topics.

Run on the pod (or anywhere with the procedures corpus loaded):

  python scripts/test_classic_rag_composite.py
  python scripts/test_classic_rag_composite.py --live   # also POST /chat (classic mode)

Environment (optional, for --live):
  API_BASE_URL=http://127.0.0.1:8000
  USER_USERNAME=user
  USER_PASSWORD=user1234
  TEST_CATEGORY=procedures
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app_config.settings import settings  # noqa: E402
from core.chat_policy import detect_lang_bucket, retrieval_anchor_query  # noqa: E402
from core.documents import get_store  # noqa: E402

COMPOSITE_CASES: list[dict[str, Any]] = [
    {
        "id": "coords_return_refund",
        "question": (
            "Un vendeur veut modifier le numéro de téléphone du client pendant une livraison, "
            "traiter un retour colis et lancer une demande de remboursement. "
            "Quelles sont les étapes principales pour chaque cas ?"
        ),
        "expected_topics": ("coordonn", "retour", "remboursement"),
        "min_docs": 3,
    },
    {
        "id": "unreachable_pickup_address",
        "question": (
            "Comment gérer un client injoignable, reprogrammer un ramassage chez le vendeur "
            "et mettre à jour l'adresse de livraison d'un colis déjà expédié ?"
        ),
        "expected_topics": ("injoignable", "ramassage", "adresse"),
        "min_docs": 3,
    },
    {
        "id": "darija_mixed",
        "question": (
            "Vendor kaybghi ybdel numéro dyal client f livraison, w client ma kayjawebch, "
            "w bghina ndiro retour — chno les étapes l kol wa7ed?"
        ),
        "expected_topics": ("numéro", "injoignable", "retour"),
        "min_docs": 3,
    },
    {
        "id": "litige_tracking_stock",
        "question": (
            "Procédure pour ouvrir un litige livraison, vérifier le tracking d'un colis "
            "bloqué en statut anormal, et corriger une erreur de stock sur la plateforme ?"
        ),
        "expected_topics": ("litige", "tracking", "stock"),
        "min_docs": 3,
    },
]


def _topic_hits(text: str, topics: tuple[str, ...]) -> dict[str, bool]:
    low = (text or "").lower()
    return {t: t.lower() in low for t in topics}


def evaluate_bm25(case: dict[str, Any], category: str) -> dict[str, Any]:
    store = get_store()
    cats = store.resolve_rag_scope(category)
    q = case["question"]
    bucket = detect_lang_bucket(q)
    rq = retrieval_anchor_query(q, [])
    expand = bucket in ("fr", "darija", "en")
    k = max(1, int(settings.RAG_RETRIEVAL_CANDIDATE_K))

    ranked = store.retrieve(
        rq,
        categories=cats,
        k=k,
        expand_fr_darija_hints=expand,
    )
    doc_names = [d.name for d in ranked]
    unique_docs = list(dict.fromkeys(doc_names))

    ctx = store.build_context(
        rq,
        categories=cats,
        k=k,
        max_chars=settings.RAG_INJECT_MAX_CHARS,
        expand_fr_darija_hints=expand,
        condense=settings.RAG_CONDENSE_DOCUMENTS,
    )
    ctx_docs = []
    if ctx:
        for line in ctx.splitlines():
            if line.startswith("### Document :"):
                ctx_docs.append(line.replace("### Document :", "").strip())

    topic_in_ctx = _topic_hits(ctx or "", case["expected_topics"])
    topic_in_corpus = {}
    for cat in cats:
        idx = store.indexes.get(cat)
        if not idx:
            continue
        merged = "\n".join(d.text for d in idx.docs)
        for t, hit in _topic_hits(merged, case["expected_topics"]).items():
            topic_in_corpus[t] = topic_in_corpus.get(t, False) or hit

    bm25_ok = len(unique_docs) >= int(case["min_docs"])
    topics_in_ctx = sum(1 for v in topic_in_ctx.values() if v)
    topics_in_corpus = sum(1 for v in topic_in_corpus.values() if v)

    return {
        "id": case["id"],
        "bm25_unique_docs": len(unique_docs),
        "bm25_top": unique_docs[:8],
        "ctx_docs": ctx_docs[:8],
        "ctx_chars": len(ctx or ""),
        "topics_in_ctx": topic_in_ctx,
        "topics_in_corpus": topic_in_corpus,
        "bm25_ok": bm25_ok,
        "topics_ok": topics_in_ctx >= min(2, topics_in_corpus),
        "verdict": "pass" if bm25_ok and topics_in_ctx >= min(2, topics_in_corpus) else "review",
    }


def live_chat(case: dict[str, Any], category: str, cookies) -> dict[str, Any]:
    import httpx

    api = os.environ.get("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    payload = {
        "message": case["question"],
        "category": category,
        "agentic_rag": False,
        "conversation_history": [],
    }
    with httpx.Client(timeout=180.0) as client:
        r = client.post(f"{api}/chat", json=payload, cookies=cookies)
        r.raise_for_status()
        data = r.json()
    answer = (data.get("response") or data.get("message") or "").strip()
    rag = data.get("rag") or {}
    low = answer.lower()
    not_found = any(
        m in low
        for m in (
            "pas trouvé",
            "could not find",
            "absente des documents",
            "absente des procédures",
            "ma لqit",
        )
    )
    return {
        "answer_preview": answer[:400],
        "not_found": not_found,
        "ctx_chars": rag.get("context_chars"),
        "docs_in_prompt": rag.get("documents_in_prompt"),
        "verdict": "pass" if not not_found and len(answer) > 120 else "review",
    }


def login_cookies():
    import httpx

    api = os.environ.get("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    user = os.environ.get("USER_USERNAME", "user")
    password = os.environ.get("USER_PASSWORD", "user1234")
    with httpx.Client(timeout=30.0) as client:
        r = client.post(f"{api}/auth/login", json={"username": user, "password": password})
        r.raise_for_status()
        return r.cookies


def main() -> int:
    parser = argparse.ArgumentParser(description="Composite classic RAG evaluation")
    parser.add_argument("--live", action="store_true", help="Also call /chat in classic mode")
    parser.add_argument("--category", default=os.environ.get("TEST_CATEGORY", "procedures"))
    args = parser.parse_args()

    store = get_store()
    cats = store.resolve_rag_scope(args.category)
    if not cats:
        print(f"No category resolved for {args.category!r}")
        return 1

    idx = store.indexes.get(cats[0])
    print("=== Classic RAG composite test ===")
    print(f"Category: {args.category} -> {cats}")
    if idx:
        print(f"Corpus: {len(idx.docs)} docs")
        print("Sample docs:", ", ".join(d.name for d in idx.docs[:12]))
    print()

    cookies = login_cookies() if args.live else None
    results = []
    failed = 0

    for case in COMPOSITE_CASES:
        print(f"--- {case['id']} ---")
        print(case["question"][:180] + ("…" if len(case["question"]) > 180 else ""))
        bm = evaluate_bm25(case, args.category)
        print(
            f"BM25: {bm['bm25_unique_docs']} unique docs in top-{settings.RAG_RETRIEVAL_CANDIDATE_K}, "
            f"ctx={bm['ctx_chars']} chars, topics_in_ctx={bm['topics_in_ctx']}"
        )
        print("Top BM25:", ", ".join(bm["bm25_top"][:5]) or "(none)")
        print("Injected:", ", ".join(bm["ctx_docs"][:5]) or "(none)")
        row = {"bm25": bm}
        if args.live and cookies is not None:
            live = live_chat(case, args.category, cookies)
            row["live"] = live
            print(f"Live: verdict={live['verdict']} not_found={live['not_found']} ctx={live['ctx_chars']}")
            print("Answer:", live["answer_preview"][:220])
            if live["verdict"] != "pass":
                failed += 1
        if bm["verdict"] != "pass":
            failed += 1
        print(f"BM25 verdict: {bm['verdict']}\n")
        results.append(row)

    out = REPO_ROOT / "logs" / "classic_rag_composite_results.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Results saved to {out}")

    if failed:
        print(f"{failed} case(s) need review — BM25 may miss some topics on multi-procedure questions.")
        return 0
    print("All composite cases passed BM25 retrieval checks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
