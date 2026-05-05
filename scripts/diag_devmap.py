#!/usr/bin/env python3
"""Build a custom device_map for Gemma4 multimodal Conditional Generation:
- vision_tower on cpu (unused for text)
- audio_tower (if any) on cpu
- language_model split between cuda:0 and cuda:1 contiguously
- embed_tokens, lm_head, multimodal projector, norm on cuda:0

This lets us avoid CPU offload of the language layers (which is the main
bottleneck) while keeping the unused vision/audio towers off-GPU.
"""
from __future__ import annotations

import os
import time
import torch
from accelerate import init_empty_weights, infer_auto_device_map
from transformers import AutoConfig, AutoModelForCausalLM, AutoTokenizer

MODEL_DIR = os.environ.get("MODEL_DIR", "/workspace/models/gemma4-26b-it")
PROMPT = "Reply with one short, friendly English sentence and stop."
PRINT_MAP = os.environ.get("PRINT_MAP", "1") == "1"
GPU0_MAX = os.environ.get("GPU0_MAX", "44GiB")
GPU1_MAX = os.environ.get("GPU1_MAX", "44GiB")
SPLIT_LANG_ACROSS_GPUS = os.environ.get("SPLIT_LANG", "1") == "1"

print(f"== diag_devmap (split={SPLIT_LANG_ACROSS_GPUS}) ==")
print(f"torch {torch.__version__}, n_gpu={torch.cuda.device_count()}")

t0 = time.time()
tok = AutoTokenizer.from_pretrained(MODEL_DIR, use_fast=True)
if tok.pad_token_id is None and tok.eos_token_id is not None:
    tok.pad_token_id = tok.eos_token_id
print(f"tokenizer loaded in {time.time()-t0:.1f}s")

# Build empty model so we can inspect modules
cfg = AutoConfig.from_pretrained(MODEL_DIR)
with init_empty_weights():
    skel = AutoModelForCausalLM.from_config(cfg, torch_dtype=torch.bfloat16)

# Find language_model layer count
n_layers = len(skel.model.language_model.layers)
print(f"n_layers (language_model): {n_layers}")

# Build device_map
dev_map: dict[str, str | int] = {}

# Towers we never use for text-only inference -> CPU
for name, _mod in skel.named_modules():
    if name == "model.vision_tower":
        dev_map[name] = "cpu"
    if name == "model.audio_tower":
        dev_map[name] = "cpu"
    if name == "model.embed_vision":
        dev_map[name] = "cpu"
    if name == "model.embed_audio":
        dev_map[name] = "cpu"
    if name == "model.embed_video":
        dev_map[name] = "cpu"

# Embedding + lm_head + final norm on cuda:0
dev_map["model.language_model.embed_tokens"] = 0
dev_map["model.language_model.norm"] = 0
dev_map["lm_head"] = 0
# Multi-modal projector (small) on cuda:0
for name, _mod in skel.named_modules():
    if "multi_modal" in name and name.count(".") == 1:
        dev_map[name] = 0

# Language model layers
if SPLIT_LANG_ACROSS_GPUS and torch.cuda.device_count() >= 2:
    # First half on cuda:0, second half on cuda:1
    half = n_layers // 2
    for i in range(n_layers):
        dev_map[f"model.language_model.layers.{i}"] = 0 if i < half else 1
    print(f"split layers: 0..{half-1} on cuda:0, {half}..{n_layers-1} on cuda:1")
else:
    for i in range(n_layers):
        dev_map[f"model.language_model.layers.{i}"] = 0

if PRINT_MAP:
    print("device_map summary (sample):")
    for k in list(dev_map.keys())[:5]:
        print(f"  {k}: {dev_map[k]}")
    print(f"  ... +{len(dev_map)-5} entries")

# Now load with explicit device_map
t0 = time.time()
model = AutoModelForCausalLM.from_pretrained(
    MODEL_DIR,
    dtype=torch.bfloat16,
    device_map=dev_map,
    low_cpu_mem_usage=True,
    attn_implementation="eager",
)
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
infer_dev = torch.device("cuda:0")
gen_in = {k: v.to(infer_dev) for k, v in inputs.items() if isinstance(v, torch.Tensor)}

turn_id = tok.convert_tokens_to_ids("<turn|>")
eos_ids: list[int] = []
if isinstance(turn_id, int) and turn_id != tok.unk_token_id:
    eos_ids.append(int(turn_id))
if isinstance(tok.eos_token_id, int) and tok.eos_token_id not in eos_ids:
    eos_ids.append(int(tok.eos_token_id))

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
