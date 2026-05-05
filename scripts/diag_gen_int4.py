#!/usr/bin/env python3
"""Try INT4 NF4 single-GPU and BF16 multi-GPU on Gemma4. Print real generations.

Run with:
    CUDA_VISIBLE_DEVICES=0 python3 scripts/diag_gen_int4.py
or:
    CUDA_VISIBLE_DEVICES=0,1 GEN_MODE=bf16_multi python3 scripts/diag_gen_int4.py
"""
from __future__ import annotations

import os
import time
import traceback

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

MODEL_DIR = os.environ.get("MODEL_DIR", "/workspace/models/gemma4-26b-it")
PROMPT = "Reply with one short, friendly English sentence and stop."
MODE = os.environ.get("GEN_MODE", "int4")  # int4 | int8 | bf16_multi

print(f"== diag_gen ({MODE}) ==")
print(f"torch {torch.__version__}, CUDA {torch.version.cuda}, n_gpu={torch.cuda.device_count()}")
print(f"set_submodule on Module: {hasattr(torch.nn.Module, 'set_submodule')}")

t0 = time.time()
tok = AutoTokenizer.from_pretrained(MODEL_DIR, use_fast=True)
if tok.pad_token_id is None and tok.eos_token_id is not None:
    tok.pad_token_id = tok.eos_token_id
print(f"tokenizer loaded in {time.time()-t0:.1f}s ({type(tok).__name__})")

load_kwargs: dict = dict(
    low_cpu_mem_usage=True,
    attn_implementation=os.environ.get("ATTN", "eager"),
)

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
    load_kwargs["torch_dtype"] = torch.bfloat16
    load_kwargs["device_map"] = "auto"
    n = torch.cuda.device_count()
    if n > 0:
        load_kwargs["max_memory"] = {i: "44GiB" for i in range(n)}
elif MODE == "bf16_offload":
    # Single GPU + CPU offload — slow but produces correct text.
    load_kwargs["torch_dtype"] = torch.bfloat16
    load_kwargs["device_map"] = "auto"
    load_kwargs["max_memory"] = {0: "42GiB", "cpu": "200GiB"}
elif MODE == "bf16_lm_on_gpu":
    # Hand-crafted device_map: keep language_model on cuda:0+cuda:1, vision on cpu.
    # We resolve the map at load time after a quick init; for simplicity here we
    # use a name-prefix map.
    load_kwargs["torch_dtype"] = torch.bfloat16
    load_kwargs["device_map"] = {
        "model.embed_vision": "cpu",
        "model.embed_audio": "cpu",
        "model.language_model.embed_tokens": 0,
        "model.language_model.layers.0": 0,
        "model.language_model.layers.1": 0,
        "model.language_model.layers.2": 0,
        "model.language_model.layers.3": 0,
        "model.language_model.layers.4": 0,
        "model.language_model.layers.5": 0,
        "model.language_model.layers.6": 0,
        "model.language_model.layers.7": 0,
        "model.language_model.layers.8": 0,
        "model.language_model.layers.9": 0,
        "model.language_model.layers.10": 0,
        "model.language_model.layers.11": 0,
        "model.language_model.layers.12": 0,
        "model.language_model.layers.13": 0,
        "model.language_model.layers.14": 0,
        "model.language_model.layers.15": 1,
        "model.language_model.layers.16": 1,
        "model.language_model.layers.17": 1,
        "model.language_model.layers.18": 1,
        "model.language_model.layers.19": 1,
        "model.language_model.layers.20": 1,
        "model.language_model.layers.21": 1,
        "model.language_model.layers.22": 1,
        "model.language_model.layers.23": 1,
        "model.language_model.layers.24": 1,
        "model.language_model.layers.25": 1,
        "model.language_model.layers.26": 1,
        "model.language_model.layers.27": 1,
        "model.language_model.layers.28": 1,
        "model.language_model.layers.29": 1,
        "model.language_model.norm": 1,
        "lm_head": 0,
    }
else:
    raise SystemExit(f"unknown GEN_MODE={MODE}")

t0 = time.time()
try:
    model = AutoModelForCausalLM.from_pretrained(MODEL_DIR, **load_kwargs)
except Exception as e:
    print(f"LOAD FAILED: {type(e).__name__}: {e}")
    traceback.print_exc()
    raise SystemExit(1)
print(f"model loaded in {time.time()-t0:.1f}s")
gpu_devs = sorted({str(p.device) for p in model.parameters() if p.device.type == "cuda"})
cpu_n = sum(1 for p in model.parameters() if p.device.type == "cpu")
print(f"gpu_devs={gpu_devs} cpu_params={cpu_n}")

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

# Stop on <turn|> (Gemma4 end-of-turn) AND <eos>
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
