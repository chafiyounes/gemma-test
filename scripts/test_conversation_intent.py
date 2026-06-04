#!/usr/bin/env python3
"""Unit tests for greeting / help / off-topic preflight in chat_policy."""
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
)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "thread_complex_cases.json"

CASES = [
    ("hi", "greeting"),
    ("Bonjour!", "greeting"),
    ("salut", "greeting"),
    ("can you help me?", "help_request"),
    ("Peux-tu m'aider ?", "help_request"),
    ("what can you do?", "help_request"),
    ("merci", "thanks"),
    ("thank you", "thanks"),
    ("What's the weather in Casablanca?", "off_topic"),
    ("Tell me a joke", "off_topic"),
    ("Comment modifier le numéro du client pendant une livraison ?", None),
    (
        "Vendor bghay ybdel numéro dyal client walakin colis déjà f livraison — chno ndir?",
        None,
    ),
    ("continue", None),
]


def main() -> int:
    failed = 0
    for message, expected in CASES:
        got = classify_conversation_intent(message)
        if got != expected:
            print(f"FAIL intent {message!r}: expected {expected!r}, got {got!r}")
            failed += 1
            continue
        pre = conversation_preflight_response(message)
        if expected is None:
            if pre is not None:
                print(f"FAIL preflight {message!r}: expected None, got {pre[0]!r}")
                failed += 1
            else:
                print(f"OK   {message!r} -> procedure query")
        else:
            if not pre or pre[0] != expected or not pre[1].strip():
                print(f"FAIL preflight {message!r}: {pre!r}")
                failed += 1
            else:
                print(f"OK   {message!r} -> {expected}")

    thread_cases = json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"]
    for case in thread_cases:
        msg = case["follow_up"]
        hist = case["history_prefix"]
        got = classify_conversation_intent(msg, hist)
        if got is not None:
            print(f"FAIL thread [{case['id']}] intent={got!r}")
            failed += 1
            continue
        pre = conversation_preflight_response(msg, hist)
        if pre is not None:
            print(f"FAIL thread [{case['id']}] preflight={pre[0]!r}")
            failed += 1
        else:
            print(f"OK   thread [{case['id']}] -> procedure query")

    if failed:
        print(f"\n{failed} failure(s)")
        return 1
    print(f"\nAll {len(CASES)} + {len(thread_cases)} thread cases passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
