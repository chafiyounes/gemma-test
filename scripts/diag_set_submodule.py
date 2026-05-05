#!/usr/bin/env python3
"""Probe set_submodule on this stack and try INT8 load with polyfill."""
import torch
import torch.nn as nn

print("torch:", torch.__version__)
print("nn.Module.set_submodule exists:", hasattr(nn.Module, "set_submodule"))


def _polyfill_set_submodule():
    if hasattr(nn.Module, "set_submodule"):
        return
    def set_submodule(self, target, module):
        if target == "":
            raise ValueError("set_submodule cannot replace root module")
        atoms = target.split(".")
        parent = self
        for atom in atoms[:-1]:
            if not hasattr(parent, atom):
                raise AttributeError(f"{type(parent).__name__} has no submodule {atom!r}")
            parent = getattr(parent, atom)
        setattr(parent, atoms[-1], module)
    nn.Module.set_submodule = set_submodule
    print("polyfill: installed nn.Module.set_submodule")


_polyfill_set_submodule()
print("after polyfill, exists:", hasattr(nn.Module, "set_submodule"))


def _polyfill_int8params():
    """bnb 0.49.2 Int8Params.__new__ doesn't accept the `_is_hf_initialized`
    kwarg that accelerate 1.13 passes. Wrap __new__ to swallow unknown kwargs.
    """
    try:
        import bitsandbytes.nn as bnb_nn
    except Exception:
        return
    cls = getattr(bnb_nn, "Int8Params", None)
    if cls is None:
        return
    if getattr(cls, "_polyfill_applied", False):
        return
    orig_new = cls.__new__
    import inspect
    try:
        sig = inspect.signature(orig_new)
        accepted = set(sig.parameters)
    except (TypeError, ValueError):
        accepted = set()

    def patched_new(klass, *args, **kwargs):
        if accepted and not any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
            kwargs = {k: v for k, v in kwargs.items() if k in accepted}
        else:
            kwargs.pop("_is_hf_initialized", None)
        return orig_new(klass, *args, **kwargs)

    cls.__new__ = patched_new
    cls._polyfill_applied = True
    print("polyfill: wrapped bitsandbytes Int8Params.__new__ to drop unknown kwargs")


_polyfill_int8params()

print("\n--- attempting INT8 single-GPU load ---")
import os, time
os.environ["CUDA_VISIBLE_DEVICES"] = "0"

from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

MODEL = "/workspace/models/gemma4-26b-it"
tok = AutoTokenizer.from_pretrained(MODEL, use_fast=True)
if tok.pad_token_id is None:
    tok.pad_token_id = tok.eos_token_id

t0 = time.time()
try:
    bnb = BitsAndBytesConfig(
        load_in_8bit=True,
        llm_int8_enable_fp32_cpu_offload=True,
    )
    model = AutoModelForCausalLM.from_pretrained(
        MODEL,
        quantization_config=bnb,
        device_map="auto",
        attn_implementation="eager",
    )
    print(f"INT8 load OK in {time.time()-t0:.1f}s")
    print("gpus:", sorted({str(p.device) for p in model.parameters() if p.device.type == 'cuda'}))

    chat = [{"role": "user", "content": "Say hi in one short sentence."}]
    inputs = tok.apply_chat_template(chat, add_generation_prompt=True, return_tensors="pt", return_dict=True, enable_thinking=False)
    dev = next(p.device for p in model.parameters() if p.device.type == 'cuda')
    gen_in = {k: v.to(dev) for k, v in inputs.items() if isinstance(v, torch.Tensor)}
    print("input_ids shape:", gen_in["input_ids"].shape)

    turn_id = tok.convert_tokens_to_ids("<turn|>")
    t1 = time.time()
    with torch.no_grad():
        out = model.generate(
            **gen_in,
            max_new_tokens=40,
            do_sample=False,
            pad_token_id=tok.pad_token_id,
            eos_token_id=[turn_id, tok.eos_token_id],
        )
    elapsed = time.time() - t1
    new = out[0][gen_in["input_ids"].shape[-1]:]
    raw = tok.decode(new, skip_special_tokens=False)
    clean = tok.decode(new, skip_special_tokens=True)
    print(f"GEN OK in {elapsed:.1f}s ({len(new)} tokens, {len(new)/max(elapsed,1e-3):.1f} tok/s)")
    print(f"raw  : {raw[:300]!r}")
    print(f"clean: {clean[:300]!r}")
except Exception as exc:
    print(f"FAILED: {type(exc).__name__}: {exc}")
    import traceback
    traceback.print_exc()
