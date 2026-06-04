#!/usr/bin/env python3
"""Unit tests for thread-aware retrieval_anchor_query (varied scenarios)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.chat_policy import (  # noqa: E402
    is_thread_follow_up_message,
    retrieval_anchor_query,
)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "thread_complex_cases.json"


def main() -> int:
    failed = 0
    cases = json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"]

    for case in cases:
        cid = case["id"]
        history = case["history_prefix"]
        follow = case["follow_up"]
        seed = case["seed"]

        if not is_thread_follow_up_message(follow, history):
            print(f"FAIL [{cid}] expected thread follow-up")
            failed += 1
            continue

        rq = retrieval_anchor_query(follow, history)
        if seed not in rq or follow not in rq:
            print(f"FAIL [{cid}] anchor: {rq[:120]!r}…")
            failed += 1
            continue
        print(f"OK   [{cid}] follow-up anchored on seed")

    history = cases[0]["history_prefix"]
    rq_cont = retrieval_anchor_query("continue", history)
    if cases[0]["seed"] not in rq_cont:
        print("FAIL continuation anchor")
        failed += 1
    else:
        print("OK   continuation merges prior turn")

    standalone = "Comment modifier le numéro du client pendant une livraison ?"
    rq_stand = retrieval_anchor_query(standalone, history)
    if rq_stand.strip() != standalone.strip():
        print(f"FAIL standalone over-anchored: {rq_stand!r}")
        failed += 1
    else:
        print("OK   standalone question not over-anchored")

    if failed:
        print(f"\n{failed} failure(s)")
        return 1
    print("\nAll retrieval anchor cases passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
