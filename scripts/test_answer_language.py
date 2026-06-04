#!/usr/bin/env python3
"""Answer-language detection and compliance helpers (no LLM)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.chat_policy import (  # noqa: E402
    detect_lang_bucket,
    is_continuation_message,
    resolve_answer_language,
)
from core.language_compliance import (  # noqa: E402
    compose_system_prompt_with_language,
    detect_response_language,
    response_matches_bucket,
)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "thread_complex_cases.json"

# Staff-style English with logistics vocabulary (must not classify as French).
EN_LOGISTICS = [
    (
        "i messaged a client that was marked as canceled, but he said no delivery "
        "person ever called him"
    ),
    (
        "the vendor claims the parcel was cancelled but the customer says the "
        "driver never showed up — what should I check in the app"
    ),
    "where can I see delivery attempt history for this parcel?",
    "how do I verify cancellation was done by the client and not a failed delivery?",
]

FR_QUESTIONS = [
    "Comment modifier le numéro du client pendant une livraison ?",
    (
        "Le vendeur insiste pour un remboursement alors que le colis est encore "
        "« en cours de livraison » — quelle procédure ?"
    ),
]

DARIJA_QUESTIONS = [
    "Vendor bghay ybdel numéro dyal client walakin colis déjà f livraison — chno ndir?",
    "Bghit ndir demande sortie stock — chno n9oul lih?",
]


def main() -> int:
    failed = 0

    for q in EN_LOGISTICS:
        got = detect_lang_bucket(q)
        if got != "en":
            print(f"FAIL detect_lang_bucket EN: {got!r} for {q[:60]!r}…")
            failed += 1
        else:
            print(f"OK   EN detect: {q[:50]!r}…")

    for q in FR_QUESTIONS:
        got = detect_lang_bucket(q)
        if got != "fr":
            print(f"FAIL detect_lang_bucket FR: {got!r}")
            failed += 1
        else:
            print(f"OK   FR detect")

    for q in DARIJA_QUESTIONS:
        got = detect_lang_bucket(q)
        if got != "darija":
            print(f"FAIL detect_lang_bucket darija: {got!r}")
            failed += 1
        else:
            print(f"OK   darija detect")

    darija_seed = DARIJA_QUESTIONS[0]
    hist = [{"role": "user", "content": darija_seed}, {"role": "assistant", "content": "…"}]
    en_follow = EN_LOGISTICS[2]
    got = resolve_answer_language(en_follow, hist)
    if got != "en":
        print(f"FAIL latest-wins: English after Darija thread got {got!r}")
        failed += 1
    else:
        print("OK   latest message wins (EN after Darija history)")

    if not is_continuation_message("continue"):
        print("FAIL continue should be continuation")
        failed += 1
    cont_bucket = resolve_answer_language(
        "continue",
        [{"role": "user", "content": darija_seed}, {"role": "assistant", "content": "x"}],
    )
    if cont_bucket != "darija":
        print(f"FAIL continuation inherits darija, got {cont_bucket!r}")
        failed += 1
    else:
        print("OK   continuation inherits prior user language")

    sys_en = compose_system_prompt_with_language("## Priorité\n- test", "en")
    if "OUTPUT LANGUAGE" not in sys_en or "ENGLISH" not in sys_en:
        print("FAIL compose_system_prompt_with_language en")
        failed += 1
    else:
        print("OK   language block injected in system prompt")

    fr_open = "D'après les procédures de SENDIT, voici les éléments pour comprendre."
    if response_matches_bucket(fr_open, "en"):
        print("FAIL French opening should not match en bucket")
        failed += 1
    else:
        print("OK   response_matches_bucket rejects French opening for en")

    en_open = "According to the procedures, here is what you should check."
    if detect_response_language(en_open) != "en":
        print(f"FAIL detect_response_language en: {detect_response_language(en_open)!r}")
        failed += 1
    else:
        print("OK   detect_response_language English opening")

    cases = json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"]
    for case in cases:
        cid = case["id"]
        expect = case["expect_bucket"]
        follow = case["follow_up"]
        hist_case = case["history_prefix"]
        got = resolve_answer_language(follow, hist_case)
        if got != expect:
            print(f"FAIL fixture [{cid}] expected {expect!r}, got {got!r}")
            failed += 1
        else:
            print(f"OK   fixture [{cid}] bucket {got!r}")

    if failed:
        print(f"\n{failed} failure(s)")
        return 1
    print("\nAll answer-language checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
