#!/usr/bin/env python3
"""Run a tiny end-to-end generation to find a working Gemma4 config.

Tries (in order): INT4 single-GPU, INT8 single-GPU, BF16 multi-GPU, BF16 single-GPU.
Prints the actual decoded text for each.
"""
from __future__ import annotations

import os
import time
import traceback

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

MODEL_DIR = os.environ.get("MODEL_DIR", "/workspace/models/gemma4-26b-it")
PROMPT = "Say hi in one short sentence."


def attempt(label: str, **load_kwargs):
    print(f"\n========== {label} ==========")
    print(f"kwargs: {{k: type(v).__name__ for k,v in load_kwargs.items()}}")
    print(f"GPUs visible: {os.environ.get('CUDA_VISIBLE_DEVICES', 'all')}")
    t0 = time.time()
    try:
        tok = AutoTokenizer.from_pretrained(MODEL_DIR, use_fast=True)
        if tok.pad_token_id is None and tok.eos_token_id is not None:
            tok.pad_token_id = tok.eos_token_id
        print(f"tok loaded ({type(tok).__name__}) in {time.time()-t0:.1f}s")

        t0 = time.time()
        model = AutoModelForCausalLM.from_pretrained(MODEL_DIR, **load_kwargs)
        print(f"model loaded in {time.time()-t0:.1f}s")
        gpu_devs = sorted({str(p.device) for p in model.parameters() if p.device.type == 'cuda'})
        print(f"gpu_devs: {gpu_devs}")

        chat = [{"role": "user", "content": PROMPT}]
        inputs = tok.apply_chat_template(chat, add_generation_prompt=True, return_tensors="pt", return_dict=True)
        infer_dev = next(p.device for p in model.parameters() if p.device.type == 'cuda')
        gen_in = {k: v.to(infer_dev) for k, v in inputs.items() if isinstance(v, torch.Tensor)}
        print(f"input_ids shape: {gen_in['input_ids'].shape}, dev={infer_dev}")

        t0 = time.time()
        with torch.no_grad():
            out = model.generate(
                **gen_in,
                max_new_tokens=40,
                do_sample=False,
                pad_token_id=tok.pad_token_id,
                eos_token_id=tok.eos_token_id,
            )
        elapsed = time.time() - t0
        new = out[0][gen_in["input_ids"].shape[-1]:]
        text = tok.decode(new, skip_special_tokens=True).strip()
        raw = tok.decode(new, skip_special_tokens=False)
        print(f"GEN OK in {elapsed:.1f}s ({len(new)} tokens, {len(new)/max(elapsed,1e-3):.1f} tok/s)")
        print(f"clean: {text!r}")
        print(f"raw:   {raw!r}")
        return True
    except Exception as exc:
        print(f"FAILED: {type(exc).__name__}: {exc}")
        traceback.print_exc()
        return False
    finally:
        try:
            del model
        except Exception:
            pass
        torch.cuda.empty_cache()


def main():
    os.environ["CUDA_VISIBLE_DEVICES"] = os.environ.get("CUDA_VISIBLE_DEVICES", "0")

    if attempt("INT4 NF4 single-GPU + eager",
               quantization_config=BitsAndBytesConfig(
                   load_in_4bit=True,
                   bnb_4bit_compute_dtype=torch.bfloat16,
                   bnb_4bit_quant_type="nf4",
                   bnb_4bit_use_double_quant=True,
               ),
               device_map="auto",
               attn_implementation="eager"):
        return

    if attempt("INT8 single-GPU + eager",
               quantization_config=BitsAndBytesConfig(load_in_8bit=True),
               device_map="auto",
               attn_implementation="eager"):
        return

    os.environ["CUDA_VISIBLE_DEVICES"] = "0,1"
    if attempt("BF16 multi-GPU + eager",
               torch_dtype=torch.bfloat16,
               device_map="auto",
               low_cpu_mem_usage=True,
               attn_implementation="eager"):
        return

    print("\nALL CONFIGS FAILED")


if __name__ == "__main__":
    main()
