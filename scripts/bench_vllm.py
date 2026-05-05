#!/usr/bin/env python3
"""Tiny benchmark for the vLLM OpenAI-compatible /v1/chat/completions endpoint."""
from __future__ import annotations
import argparse, json, os, sys, time, urllib.request

DEFAULT_PROMPTS = [
    ("french_intro",
     "Bonjour ! En 3 phrases, qui es-tu et que peux-tu faire ? Réponds en français."),
    ("english_explain",
     "Explain in 4 sentences how a transformer language model works."),
    ("arabic_intro",
     "Réponds en darija marocaine: Salam ! Achno smiyetek u 3lach katsta3mel l3aql l istina3i ?"),
    ("code_short",
     "Write a short Python function that returns the n-th Fibonacci number iteratively."),
]


def call(host: str, model: str, prompt: str, max_tokens: int, temperature: float) -> dict:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{host.rstrip('/')}/v1/chat/completions",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=600) as r:
        data = json.loads(r.read().decode("utf-8"))
    t1 = time.perf_counter()
    data["_elapsed_s"] = t1 - t0
    return data


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="http://localhost:8002")
    ap.add_argument("--model", default="gemma4-26b-it")
    ap.add_argument("--max-tokens", type=int, default=128)
    ap.add_argument("--temperature", type=float, default=0.3)
    ap.add_argument("--prompts", nargs="*", default=None,
                    help="Override prompts. If omitted, uses the built-in suite.")
    args = ap.parse_args()

    prompts = (
        [(f"custom_{i}", p) for i, p in enumerate(args.prompts)]
        if args.prompts else DEFAULT_PROMPTS
    )

    total_completion_tokens = 0
    total_elapsed = 0.0
    print(f"── target {args.host}  |  model={args.model}")
    for name, prompt in prompts:
        print(f"\n[{name}] {prompt[:80]}")
        try:
            d = call(args.host, args.model, prompt, args.max_tokens, args.temperature)
        except Exception as e:
            print(f"  ✗ request failed: {type(e).__name__}: {e}")
            continue
        usage = d.get("usage", {})
        ct = int(usage.get("completion_tokens", 0))
        pt = int(usage.get("prompt_tokens", 0))
        elapsed = float(d["_elapsed_s"])
        tps = (ct / elapsed) if elapsed > 0 else 0.0
        msg = d["choices"][0]["message"]["content"].strip()
        print(f"  ── {ct} completion tokens / {pt} prompt / {elapsed:.2f}s = {tps:.2f} tok/s")
        snippet = msg if len(msg) <= 280 else msg[:277] + "…"
        print(f"  └ {snippet}")
        total_completion_tokens += ct
        total_elapsed += elapsed

    if total_elapsed > 0:
        avg = total_completion_tokens / total_elapsed
        print(f"\n── total: {total_completion_tokens} tokens in {total_elapsed:.2f}s "
              f"=> avg {avg:.2f} tok/s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
