#!/usr/bin/env python3
"""Offline retrieval checks for reasoning fixtures (no LLM required).

  python scripts/eval_reasoning.py
  python scripts/eval_reasoning.py --live   # POST /chat when API is up
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app_config.settings import settings  # noqa: E402
from core.case_brief import retrieval_query_with_brief  # noqa: E402
from core.chat_policy import retrieval_anchor_query  # noqa: E402
from core.documents import get_store  # noqa: E402

FIXTURE = REPO_ROOT / "scripts" / "fixtures" / "reasoning_cases.json"


def _doc_titles(hits: list) -> str:
    parts = []
    for h in hits:
        parts.append(getattr(h, "name", "") or "")
        parts.append(getattr(h, "category", "") or "")
    return " ".join(parts).lower()


def eval_retrieval_case(case: dict[str, Any]) -> Optional[List[str]]:
    """None = skipped (no local corpus); [] = pass; non-empty = failures."""
    errors: List[str] = []
    store = get_store()
    cat = (case.get("category") or "procedures").strip()
    cid = case.get("id", "?")
    if cat not in store.indexes:
        print(f"SKIP {cid} (category {cat!r} not loaded — run on pod)")
        return None
    idx = store.indexes.get(cat)
    if not idx or not idx.docs:
        print(f"SKIP {cid} (no docs in {cat!r} — run on pod)")
        return None
    q = case["question"]
    hist = case.get("history") or []
    rq = retrieval_anchor_query(q, hist)
    bucket_expand = True
    k = min(20, max(settings.RAG_BM25_K, 12))
    hits = store.retrieve(
        rq,
        category=cat,
        k=k,
        expand_fr_darija_hints=bucket_expand,
    )
    blob = _doc_titles(hits)
    must_all = case.get("must_retrieve_substrings") or []
    for sub in must_all:
        if sub.lower() not in blob:
            errors.append(f"retrieval missing substring {sub!r} in top-{k}")
    must_any = case.get("must_retrieve_any") or []
    if must_any and not any(s.lower() in blob for s in must_any):
        errors.append(
            f"retrieval missing all of {must_any!r} in top-{k} (need at least one)"
        )
    prefer_over = case.get("prefer_retrieve_over") or []
    if prefer_over:
        bad_rank = sum(1 for p in prefer_over if p.lower() in blob[: len(blob) // 2])
        good_rank = sum(1 for s in case.get("must_retrieve_substrings") or [] if s.lower() in blob)
        if bad_rank > good_rank and good_rank == 0:
            errors.append(f"retrieval skewed toward {prefer_over!r}")
    return errors


def eval_live_case(case: dict[str, Any], base_url: str, user: str, password: str) -> list[str]:
    import httpx  # noqa: PLC0415

    errors: List[str] = []
    hist = case.get("history") or []
    with httpx.Client(base_url=base_url.rstrip("/"), timeout=120.0) as client:
        login = client.post(
            "/auth/login",
            json={"username": user, "password": password},
        )
        if login.status_code != 200:
            errors.append(f"login failed {login.status_code}")
            return errors
        cookies = login.cookies
        body: dict[str, Any] = {
            "message": case["question"],
            "category": case.get("category") or "procedures",
            "conversation_history": hist,
        }
        r = client.post("/chat", json=body, cookies=cookies)
        if r.status_code != 200:
            errors.append(f"/chat {r.status_code}: {r.text[:200]}")
            return errors
        data = r.json()
        text = (data.get("response") or "").lower()
        for bad in case.get("must_not_contain") or []:
            if bad.lower() in text:
                errors.append(f"response contains forbidden {bad!r}")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--api-base", default=os.environ.get("API_BASE_URL", "http://127.0.0.1:8000"))
    args = parser.parse_args()
    cases = json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"]
    failed = 0
    skipped = 0
    passed = 0
    for case in cases:
        cid = case["id"]
        errs = eval_retrieval_case(case)
        if errs is None:
            skipped += 1
            continue
        if args.live:
            user = os.environ.get("USER_USERNAME", "user")
            pwd = os.environ.get("USER_PASSWORD", "user1234")
            errs = list(errs) + eval_live_case(case, args.api_base, user, pwd)
        if errs:
            failed += 1
            print(f"FAIL {cid}:")
            for e in errs:
                print(f"  - {e}")
        else:
            passed += 1
            print(f"OK   {cid}")
    if failed:
        print(f"\n{failed} failed, {passed} passed, {skipped} skipped")
        sys.exit(1)
    print(
        f"\n{passed} passed, {skipped} skipped"
        + (" (+ live)" if args.live else "")
        + "."
    )


if __name__ == "__main__":
    main()
