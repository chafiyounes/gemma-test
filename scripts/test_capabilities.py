#!/usr/bin/env python3
"""
test_capabilities.py — Automated tests for Darija and Arabizi understanding
across the three models: Gemma base, GemMaroc-27b-it, and Atlas-Chat-27B.

Run on the pod (vLLM must be up):
    python3 scripts/test_capabilities.py --model gemma
    python3 scripts/test_capabilities.py --model gemmaroc
    python3 scripts/test_capabilities.py --model atlaschat
    python3 scripts/test_capabilities.py --all          # run all three

Results are printed to stdout AND saved to  logs/test_results_<model>.json
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

VLLM_URL = "http://localhost:8001"
# Map CLI alias → vLLM --served-model-name value
MODEL_ALIASES = {
    "gemma":     "gemma",
    "gemmaroc":  "gemmaroc",
    "atlaschat": "atlaschat",
}

# ─────────────────────────────────────────────────────────────────────────────
# Test prompts
# ─────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = (
    "You are a helpful multilingual assistant. "
    "You understand Moroccan Darija (in Arabic script and in Arabizi/Latin), "
    "Modern Standard Arabic, French, and English. "
    "Respond naturally in the same language/script the user uses."
)

TEST_CASES = [
    # ── Darija (Arabic script) ────────────────────────────────────────────
    {
        "id": "darija_ar_greeting",
        "category": "darija_arabic",
        "prompt": "كيداير؟",
        "expected_language": "darija_arabic",
        "description": "Basic Darija greeting (kif dayr?) in Arabic script",
    },
    {
        "id": "darija_ar_weather",
        "category": "darija_arabic",
        "prompt": "شحال كتاخد التاكسي من كازا لرباط؟",
        "expected_language": "darija_arabic",
        "description": "How much is a taxi from Casablanca to Rabat?",
    },
    {
        "id": "darija_ar_market",
        "category": "darija_arabic",
        "prompt": "واش عندك شي واحد رخيص فالسوق؟",
        "expected_language": "darija_arabic",
        "description": "Do you have something cheap at the market?",
    },
    {
        "id": "darija_ar_codeswitching",
        "category": "darija_arabic",
        "prompt": "بغيت نشري telephone جديد، شنو عندك فالمخزن؟",
        "expected_language": "darija_arabic",
        "description": "Darija-French code-switching (want to buy a new phone)",
    },
    # ── Arabizi (Darija in Latin script with numbers) ─────────────────────
    {
        "id": "arabizi_greeting",
        "category": "arabizi",
        "prompt": "kif dayr? labas 3lik?",
        "expected_language": "arabizi",
        "description": "Arabizi greeting — how are you?",
    },
    {
        "id": "arabizi_numbers",
        "category": "arabizi",
        "prompt": "3ندek chi 7aja zwina f souk?",
        "expected_language": "arabizi",
        "description": "Arabizi with digit substitutions: 3=ع, 7=ح",
    },
    {
        "id": "arabizi_question",
        "category": "arabizi",
        "prompt": "fin kayn chi restaurant mezyan f casa?",
        "expected_language": "arabizi",
        "description": "Where is a good restaurant in Casablanca? (Arabizi)",
    },
    {
        "id": "arabizi_mixed_french",
        "category": "arabizi",
        "prompt": "bghit ndir reservation f un hotel, ki ndir?",
        "expected_language": "arabizi",
        "description": "Arabizi + French code-switch: I want to make a hotel reservation, how?",
    },
    {
        "id": "arabizi_slang",
        "category": "arabizi",
        "prompt": "wach nta ok? mzyan kolchi?",
        "expected_language": "arabizi",
        "description": "Arabizi slang: are you ok? is everything good?",
    },
    # ── French (common in Morocco alongside Darija) ───────────────────────
    {
        "id": "french_basic",
        "category": "french",
        "prompt": "Quel est le plat marocain le plus populaire?",
        "expected_language": "french",
        "description": "What is the most popular Moroccan dish? (French)",
    },
    # ── English ───────────────────────────────────────────────────────────
    {
        "id": "english_basic",
        "category": "english",
        "prompt": "What is couscous and where does it come from?",
        "expected_language": "english",
        "description": "Simple English factual question about Moroccan food",
    },
    # ── Comprehension / complex Darija ────────────────────────────────────
    {
        "id": "darija_comprehension",
        "category": "darija_arabic",
        "prompt": (
            "ش بغيت نسافر للمغرب. شنو خاصني نعرف قبل ما نجي؟ "
            "مثلا: الفيزا، الفلوس، والأماكن المزيانة باش نزور."
        ),
        "expected_language": "darija_arabic",
        "description": "Complex travel question in Darija (visa, money, places to visit)",
    },
    {
        "id": "arabizi_comprehension",
        "category": "arabizi",
        "prompt": (
            "bghit nsafar l lmaghrib, chno khassni n3raf? "
            "visa, flous, o wach kayn chi application tzid f smartphone?"
        ),
        "expected_language": "arabizi",
        "description": "Same travel question in Arabizi (with app question)",
    },
]


# ─────────────────────────────────────────────────────────────────────────────

def call_vllm(model_name: str, prompt: str, system_prompt: str) -> dict:
    """Send a single prompt to vLLM and return the response dict."""
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 512,
        "temperature": 0.3,
    }
    with httpx.Client(timeout=120.0) as client:
        resp = client.post(f"{VLLM_URL}/v1/chat/completions", json=payload)
        resp.raise_for_status()
        data = resp.json()
        return {
            "text": data["choices"][0]["message"]["content"].strip(),
            "finish_reason": data["choices"][0].get("finish_reason"),
            "usage": data.get("usage", {}),
        }


def run_tests(model_alias: str) -> list[dict]:
    model_name = MODEL_ALIASES[model_alias]
    results = []
    print(f"\n{'═' * 60}")
    print(f"  Testing model: {model_alias}  (served as '{model_name}')")
    print(f"{'═' * 60}\n")

    for i, tc in enumerate(TEST_CASES, 1):
        print(f"  [{i:02d}/{len(TEST_CASES)}] {tc['id']}  ({tc['category']})")
        print(f"        Prompt: {tc['prompt'][:80]}")

        start = time.time()
        try:
            result = call_vllm(model_name, tc["prompt"], SYSTEM_PROMPT)
            elapsed = time.time() - start
            response_text = result["text"]
            error = None
        except Exception as exc:
            elapsed = time.time() - start
            response_text = ""
            error = str(exc)
            print(f"        ✗ ERROR: {exc}")

        # Quick heuristic: did the model respond in the expected script/language?
        detected_script = _detect_script(response_text)
        expected_ok = _check_expected(tc["expected_language"], response_text, detected_script)

        record = {
            "model": model_alias,
            "id": tc["id"],
            "category": tc["category"],
            "description": tc["description"],
            "prompt": tc["prompt"],
            "response": response_text,
            "expected_language": tc["expected_language"],
            "detected_script": detected_script,
            "expected_ok": expected_ok,
            "elapsed_s": round(elapsed, 2),
            "error": error,
        }
        results.append(record)

        if error:
            print(f"        ✗ FAILED ({elapsed:.1f}s)")
        else:
            status_icon = "✓" if expected_ok else "⚠"
            first_line = response_text.split("\n")[0][:100]
            print(f"        {status_icon} Response ({elapsed:.1f}s): {first_line}")
        print()

    return results


def _detect_script(text: str) -> str:
    """Rough detection of the response script."""
    if not text:
        return "empty"
    arabic_chars = sum(1 for c in text if "\u0600" <= c <= "\u06FF")
    total_chars = len(text.replace(" ", "").replace("\n", ""))
    if total_chars == 0:
        return "empty"
    arabic_ratio = arabic_chars / total_chars
    if arabic_ratio > 0.4:
        return "arabic_script"
    # French/English/Arabizi heuristic
    latin_chars = sum(1 for c in text if c.isalpha() and c.isascii())
    if latin_chars > 0:
        return "latin"
    return "unknown"


def _check_expected(expected_lang: str, response: str, detected_script: str) -> bool:
    """Rough check whether response matches expected output language."""
    if not response:
        return False
    if expected_lang in ("darija_arabic",):
        return detected_script == "arabic_script"
    if expected_lang == "arabizi":
        # Arabizi uses Latin — accept if model responds in Latin or Arabic
        # (some models transliterate back to Arabic which is still correct)
        return detected_script in ("latin", "arabic_script")
    if expected_lang == "french":
        return detected_script == "latin"
    if expected_lang == "english":
        return detected_script == "latin"
    return True


def print_summary(all_results: list[dict]) -> None:
    print("\n" + "═" * 60)
    print("  SUMMARY")
    print("═" * 60)

    by_model: dict[str, list] = {}
    for r in all_results:
        by_model.setdefault(r["model"], []).append(r)

    for model, results in by_model.items():
        total = len(results)
        ok = sum(1 for r in results if r["expected_ok"] and not r["error"])
        errors = sum(1 for r in results if r["error"])
        by_cat: dict[str, list] = {}
        for r in results:
            by_cat.setdefault(r["category"], []).append(r)

        print(f"\n  {model}:  {ok}/{total} passed  ({errors} errors)")
        for cat, cat_results in sorted(by_cat.items()):
            cat_ok = sum(1 for r in cat_results if r["expected_ok"] and not r["error"])
            print(f"    {cat:<20} {cat_ok}/{len(cat_results)}")


def main():
    parser = argparse.ArgumentParser(description="Darija/Arabizi capability tests")
    parser.add_argument("--model", choices=list(MODEL_ALIASES.keys()), help="Which model to test")
    parser.add_argument("--all", action="store_true", help="Test all three models")
    args = parser.parse_args()

    if not args.all and not args.model:
        parser.print_help()
        sys.exit(1)

    # Quick health check
    try:
        with httpx.Client(timeout=5.0) as c:
            c.get(f"{VLLM_URL}/health").raise_for_status()
    except Exception as exc:
        print(f"✗ vLLM not reachable at {VLLM_URL}: {exc}")
        print("  Start it first:  bash scripts/start_vllm.sh gemma")
        sys.exit(1)

    models_to_test = list(MODEL_ALIASES.keys()) if args.all else [args.model]
    all_results = []

    for model_alias in models_to_test:
        results = run_tests(model_alias)
        all_results.extend(results)

    print_summary(all_results)

    # Save results
    log_dir = Path("/workspace/gemma-test/logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = log_dir / f"test_results_{timestamp}.json"
    out_file.write_text(json.dumps(all_results, ensure_ascii=False, indent=2))
    print(f"\n✓ Results saved to {out_file}")


if __name__ == "__main__":
    main()
