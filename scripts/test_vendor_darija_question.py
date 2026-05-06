#!/usr/bin/env python3
"""Integration test: POST the vendor + téléphone + livraison Darija question to /chat.

Requires a running API + vLLM (e.g. on the pod). Auth with user password.

  API_URL=http://localhost:8000 USER_PASSWORD=yourpass python scripts/test_vendor_darija_question.py

Exit 0 always; inspect stdout. Fails loudly on HTTP errors.
"""
from __future__ import annotations

import json
import os
import sys

import httpx

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

QUESTION = (
    "Vendor bghay ybdel numéro de téléphone dyal client dyalo walakin colis "
    "déjà f livraison — chno hiya les étapes li ntebi3hom?"
)


def main() -> None:
    api = os.environ.get("API_URL", "http://localhost:8000").rstrip("/")
    password = os.environ.get("USER_PASSWORD", "")
    if not password:
        print("Set USER_PASSWORD in the environment (user site password).")
        sys.exit(1)

    with httpx.Client(timeout=httpx.Timeout(300.0)) as client:
        r = client.post(f"{api}/auth/login", json={"password": password})
        r.raise_for_status()
        cookies = r.cookies
        r2 = client.post(
            f"{api}/chat",
            cookies=cookies,
            json={
                "message": QUESTION,
                "user_id": "rag-regression-test",
                "session_id": "rag-regression-session",
                "conversation_history": [],
                "category": "procedures",
            },
        )
        r2.raise_for_status()
        data = r2.json()
    print("=== /chat response ===")
    print(data.get("response", ""))
    print()
    print("=== metadata.rag ===")
    print(json.dumps(data.get("metadata", {}).get("rag"), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
