#!/usr/bin/env python3
"""Regression checks for multi-turn SENDIT chat policy (no LLM, varied scenarios)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.chat_policy import (  # noqa: E402
    classify_conversation_intent,
    conversation_preflight_response,
    resolve_answer_language,
    retrieval_anchor_query,
)

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "thread_complex_cases.json"


def main() -> int:
    data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    cases = data["cases"]
    failed = 0

    for case in cases:
        cid = case["id"]
        history = case["history_prefix"]
        follow = case["follow_up"]
        seed = case["seed"]
        expect_bucket = case["expect_bucket"]
        expect_off_topic = case["expect_off_topic"]

        intent = classify_conversation_intent(follow, history)
        if expect_off_topic:
            if intent != "off_topic":
                print(f"FAIL [{cid}] expected off_topic, got {intent!r}")
                failed += 1
            else:
                print(f"OK   [{cid}] off_topic as expected")
            continue

        if intent is not None:
            print(f"FAIL [{cid}] follow-up blocked: intent={intent!r}")
            failed += 1
            continue

        pre = conversation_preflight_response(follow, history)
        if pre is not None:
            print(f"FAIL [{cid}] preflight={pre[0]!r}")
            failed += 1
            continue

        bucket = resolve_answer_language(follow, history)
        if bucket != expect_bucket:
            print(f"FAIL [{cid}] bucket expected {expect_bucket!r}, got {bucket!r}")
            failed += 1
            continue

        rq = retrieval_anchor_query(follow, history)
        if seed not in rq:
            print(f"FAIL [{cid}] anchor missing seed")
            failed += 1
            continue

        print(f"OK   [{cid}] thread policy + anchor")

    weather = classify_conversation_intent("What's the weather in Casablanca?", [])
    if weather != "off_topic":
        print(f"FAIL unrelated question should be off_topic, got {weather!r}")
        failed += 1
    else:
        print("OK   unrelated question still off_topic")

    if failed:
        print(f"\n{failed} failure(s)")
        return 1
    print(f"\nAll {len(cases)} thread scenarios passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
