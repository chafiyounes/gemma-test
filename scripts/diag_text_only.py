#!/usr/bin/env python3
"""Load Gemma4 as text-only Gemma4ForCausalLM (skip vision/audio wrapper).

This bypasses Gemma4ForConditionalGeneration which has the broken
multi-GPU dispatch under transformers 5.7.
"""
from __future__ import annotations

import os
import time
import traceback

import torch
from transformers import AutoTokenizer, BitsAndBytesConfig, Gemma4ForCausalLM, Gemma4TextConfig

MODEL_DIR = os.environ.get("MODEL_DIR", "/workspace/models/gemma4-26b-it")
PROMPT = "Reply with one short, friendly English sentence and stop."
MODE = os.environ.get("GEN_MODE", "bf16_multi")  # bf16_multi | int4 | int8
ATTN = os.environ.get("ATTN", "eager")

print(f"== diag_text_only ({MODE}, attn={ATTN}) ==")
print(f"torch {torch.__version__}, n_gpu={torch.cuda.device_count()}")

t0 = time.time()
tok = AutoTokenizer.from_pretrained(MODEL_DIR, use_fast=True)
if tok.pad_token_id is None and tok.eos_token_id is not None:
    tok.pad_token_id = tok.eos_token_id
print(f"tokenizer loaded in {time.time()-t0:.1f}s")

# Pull text_config out of the multimodal config so the resulting model has
# no vision/audio towers.
load_kwargs: dict = dict(low_cpu_mem_usage=True, attn_implementation=ATTN)

if MODE == "int4":
    load_kwargs["quantization_config"] = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
    )
    load_kwargs["device_map"] = "auto"
elif MODE == "int8":
    load_kwargs["quantization_config"] = BitsAndBytesConfig(load_in_8bit=True)
    load_kwargs["device_map"] = "auto"
elif MODE == "bf16_multi":
    load_kwargs["dtype"] = torch.bfloat16
    load_kwargs["device_map"] = "auto"
    n = torch.cuda.device_count()
    if n > 0:
        load_kwargs["max_memory"] = {i: "44GiB" for i in range(n)}
elif MODE == "bf16_single":
    load_kwargs["dtype"] = torch.bfloat16
    load_kwargs["device_map"] = {"": "cuda:0"}
else:
    raise SystemExit(f"unknown GEN_MODE={MODE}")

t0 = time.time()
try:
    # Gemma4ForCausalLM has its own from_pretrained. The shard files contain a
    # multimodal config so HF will load only the language_model.* weights and
    # ignore the vision/audio shards.
    model = Gemma4ForCausalLM.from_pretrained(MODEL_DIR, **load_kwargs)
except Exception as e:
    print(f"LOAD FAILED: {type(e).__name__}: {e}")
    traceback.print_exc()
    raise SystemExit(1)
elapsed = time.time() - t0
print(f"model loaded in {elapsed:.1f}s — class={type(model).__name__}")
gpu_devs = sorted({str(p.device) for p in model.parameters() if p.device.type == "cuda"})
cpu_n = sum(1 for p in model.parameters() if p.device.type == "cpu")
total_params = sum(p.numel() for p in model.parameters())
print(f"gpu_devs={gpu_devs} cpu_params={cpu_n} total_params={total_params/1e9:.1f}B")

chat = [{"role": "user", "content": PROMPT}]
try:
    inputs = tok.apply_chat_template(
        chat, add_generation_prompt=True, return_tensors="pt", return_dict=True,
        enable_thinking=False,
    )
except TypeError:
    inputs = tok.apply_chat_template(
        chat, add_generation_prompt=True, return_tensors="pt", return_dict=True,
    )
infer_dev = next(p.device for p in model.parameters() if p.device.type == "cuda")
gen_in = {k: v.to(infer_dev) for k, v in inputs.items() if isinstance(v, torch.Tensor)}
print(f"input_ids: shape={tuple(gen_in['input_ids'].shape)} dev={infer_dev}")

turn_id = tok.convert_tokens_to_ids("<turn|>")
eos_ids: list[int] = []
if isinstance(turn_id, int) and turn_id != tok.unk_token_id:
    eos_ids.append(int(turn_id))
if isinstance(tok.eos_token_id, int) and tok.eos_token_id not in eos_ids:
    eos_ids.append(int(tok.eos_token_id))
print(f"eos_ids = {eos_ids}")

t0 = time.time()
with torch.no_grad():
    out = model.generate(
        **gen_in,
        max_new_tokens=40,
        do_sample=False,
        pad_token_id=tok.pad_token_id,
        eos_token_id=eos_ids or tok.eos_token_id,
    )
elapsed = time.time() - t0
new = out[0][gen_in["input_ids"].shape[-1]:]
text = tok.decode(new, skip_special_tokens=True).strip()
raw = tok.decode(new, skip_special_tokens=False)
print(f"GEN OK in {elapsed:.1f}s ({len(new)} tok, {len(new)/max(elapsed,1e-3):.2f} tok/s)")
print(f"clean: {text!r}")
print(f"raw:   {raw!r}")
