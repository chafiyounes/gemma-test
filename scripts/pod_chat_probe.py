#!/usr/bin/env python3
"""Probe local API (/chat) and print RAG metadata for troubleshooting."""
from __future__ import annotations

import argparse
import json

import requests


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("message")
    ap.add_argument("--category", default="procedures")
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--username", default="user")
    ap.add_argument("--password", default="user1234")
    args = ap.parse_args()

    s = requests.Session()
    r = s.post(
        f"{args.base_url}/auth/login",
        json={"username": args.username, "password": args.password},
        timeout=20,
    )
    print("login", r.status_code)
    if not r.ok:
        print(r.text[:400])
        return

    payload = {
        "message": args.message,
        "conversation_history": [],
        "category": args.category,
        "skip_persist": False,
    }
    r2 = s.post(f"{args.base_url}/chat", json=payload, timeout=180)
    print("chat", r2.status_code)
    if not r2.ok:
        print(r2.text[:500])
        return
    data = r2.json()
    rag = (data.get("metadata") or {}).get("rag") or {}
    print(
        "rag:",
        json.dumps(
            {
                "category": rag.get("category"),
                "context_chars": rag.get("context_chars"),
                "documents_in_prompt": rag.get("documents_in_prompt"),
                "note": rag.get("note"),
                "retrieval_error": rag.get("retrieval_error"),
                "liked_cache_hit": rag.get("liked_cache_hit"),
                "has_context_full": "context_full" in rag,
            },
            ensure_ascii=False,
        ),
    )
    print("response:", (data.get("response") or "")[:260].replace("\n", " "))


if __name__ == "__main__":
    main()

