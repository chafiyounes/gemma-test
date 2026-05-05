#!/usr/bin/env python3
"""Diagnose Gemma4 chat template + tokenization on the pod.

Confirms which API path produces sane input_ids for generation.
"""
from __future__ import annotations

import sys
from pathlib import Path

MODEL_DIR = sys.argv[1] if len(sys.argv) > 1 else "/workspace/models/gemma4-26b-it"

print(f"[diag] MODEL_DIR={MODEL_DIR}")
print(f"[diag] python={sys.version.split()[0]}")

from transformers import AutoProcessor, AutoTokenizer  # noqa: E402

print("\n=== AutoProcessor ===")
proc = AutoProcessor.from_pretrained(MODEL_DIR)
print("processor:", type(proc).__name__)
print("inner tokenizer:", type(proc.tokenizer).__name__)

chat = [{"role": "user", "content": "Say hi in one short sentence."}]

print("\n=== apply_chat_template tokenize=False ===")
text = proc.apply_chat_template(chat, add_generation_prompt=True, tokenize=False)
print("text repr:", repr(text)[:400])

print("\n=== apply_chat_template tokenize=True return_dict=True ===")
out = proc.apply_chat_template(
    chat, add_generation_prompt=True, tokenize=True,
    return_tensors="pt", return_dict=True,
)
print("keys:", list(out.keys()))
print("input_ids.shape:", out["input_ids"].shape)
print("first 40 ids:", out["input_ids"][0, :40].tolist())
print("decoded back:", proc.tokenizer.decode(out["input_ids"][0]))

print("\n=== AutoTokenizer fallback ===")
try:
    tok = AutoTokenizer.from_pretrained(MODEL_DIR, use_fast=True)
    print("tokenizer:", type(tok).__name__)
    out2 = tok.apply_chat_template(
        chat, add_generation_prompt=True,
        return_tensors="pt", return_dict=True,
    )
    print("input_ids.shape:", out2["input_ids"].shape)
    print("first 40 ids:", out2["input_ids"][0, :40].tolist())
    print("decoded back:", tok.decode(out2["input_ids"][0]))
except Exception as exc:
    print("AutoTokenizer FAILED:", exc)
