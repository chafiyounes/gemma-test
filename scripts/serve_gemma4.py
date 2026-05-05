#!/usr/bin/env python3
"""
Minimal OpenAI-compatible chat completions server using HuggingFace transformers.

Tested config that *actually works* on 2× A40 with Gemma 4 26B-IT:
    - torch 2.5.1+cu124, transformers 5.7.0, accelerate 1.13.0
    - **single-GPU bf16 with CPU offload** for the parts that don't fit
      (multi-GPU sharding of `Gemma4ForConditionalGeneration` corrupts the
      forward pass under transformers 5.7 — produces all-`<pad>` logits.
      bnb INT4/INT8 quantization also produces wrong tokens.)
    - eager attention (sdpa is ~3× slower with CPU offload here)
    - AutoTokenizer + apply_chat_template (return_dict=True)
    - eos_token_id includes Gemma4's `<turn|>` so generation stops cleanly.
    - Output cleaned to strip thinking/tool channel markers.

Endpoints:
    GET  /health
    GET  /v1/models
    POST /v1/chat/completions
"""
from __future__ import annotations

import logging
import os
import re
import time
import uuid
from contextlib import asynccontextmanager
from typing import Optional

import torch
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("serve_gemma4")

# ── Config ─────────────────────────────────────────────────────────────────────

MODEL_DIR = os.environ.get("MODEL_DIR", "/workspace/models/gemma4-26b-it")
MAX_NEW_TOKENS = int(os.environ.get("MAX_NEW_TOKENS", "256"))
TEMPERATURE = float(os.environ.get("TEMPERATURE", "0.7"))
PORT = int(os.environ.get("PORT", "8002"))
USE_INT8 = os.environ.get("USE_INT8", "0") == "1"  # broken on Gemma4 + bnb 0.49 — keep off
USE_INT4 = os.environ.get("USE_INT4", "0") == "1"
ATTN_IMPLEMENTATION = (os.environ.get("ATTN_IMPLEMENTATION", "eager") or "eager").strip()
# How much VRAM to leave for the language model. Anything that doesn't fit
# spills to CPU. Using ~42GiB of one A40 leaves 4 GiB headroom for KV cache
# and intermediate buffers — the rest of the 26B bf16 weights (~10 GiB)
# stays in CPU RAM.
GPU0_MAX_MEMORY = os.environ.get("GPU0_MAX_MEMORY", "42GiB").strip()
CPU_MAX_MEMORY = os.environ.get("CPU_MAX_MEMORY", "200GiB").strip()
# Keep prompts well below model rotary range to avoid scatter index OOB.
MAX_PROMPT_TOKENS = int(os.environ.get("MAX_PROMPT_TOKENS", "4096"))
# Repetition penalty has caused degenerate output with Gemma4 + greedy.
# Disabled by default; opt-in via env if needed.
REPETITION_PENALTY = float(os.environ.get("REPETITION_PENALTY", "1.0"))

# Gemma4 special channel markers (response_schema in tokenizer_config).
_CHANNEL_THOUGHT_RE = re.compile(r"<\|channel>thought\n.*?<channel\|>", re.DOTALL)
_TOOL_CALL_RE = re.compile(r"<\|tool_call>.*?<tool_call\|>", re.DOTALL)
_TURN_END_RE = re.compile(r"<turn\|>.*", re.DOTALL)
_LEFTOVER_TAGS_RE = re.compile(r"<\|?[a-z_]+\|?>", re.IGNORECASE)


def _clean_gemma4_reply(text: str) -> str:
    """Strip thinking/tool-call channels and trailing turn markers from raw decode."""
    out = _CHANNEL_THOUGHT_RE.sub("", text)
    out = _TOOL_CALL_RE.sub("", out)
    out = _TURN_END_RE.sub("", out)
    out = _LEFTOVER_TAGS_RE.sub("", out)
    return out.strip()


# ── Global state ───────────────────────────────────────────────────────────────

tokenizer = None
model = None
model_id: Optional[str] = None
_infer_device: Optional[torch.device] = None
_quant_mode: str = "bf16"
_eos_ids: list[int] = []


def _load_model():
    """Load Gemma4 in the only configuration confirmed to produce correct text:
    single GPU + CPU offload, bf16, eager attention.

    Multi-GPU sharding and bnb quantization both produce garbage (all <pad>
    tokens or random Korean/Hindi/etc. characters interleaved with <pad>).
    """
    extra = {"attn_implementation": ATTN_IMPLEMENTATION} if ATTN_IMPLEMENTATION else {}

    if USE_INT4 or USE_INT8:
        bnb = (BitsAndBytesConfig(
                   load_in_4bit=True,
                   bnb_4bit_compute_dtype=torch.bfloat16,
                   bnb_4bit_quant_type="nf4",
                   bnb_4bit_use_double_quant=True,
               )
               if USE_INT4 else BitsAndBytesConfig(load_in_8bit=True))
        try:
            log.info("Trying %s quantization (NOTE: may produce garbage on Gemma4)",
                     "INT4" if USE_INT4 else "INT8")
            m = AutoModelForCausalLM.from_pretrained(
                MODEL_DIR, quantization_config=bnb, device_map="auto", **extra,
            )
            return m, ("int4" if USE_INT4 else "int8")
        except Exception as exc:
            log.warning("Quant load failed (%s) — falling back to bf16", exc)

    n_gpu = torch.cuda.device_count()
    if n_gpu < 1:
        raise RuntimeError("No CUDA GPU visible — set CUDA_VISIBLE_DEVICES=0")

    # Use only cuda:0 for compute. Anything that doesn't fit goes to CPU.
    # If the user happens to have CUDA_VISIBLE_DEVICES=0,1, accelerate would
    # try to shard the language model across both GPUs (which corrupts the
    # forward pass on Gemma4). To be safe we explicitly cap cuda:1 at 0 so
    # nothing lands there.
    max_memory: dict = {0: GPU0_MAX_MEMORY, "cpu": CPU_MAX_MEMORY}
    if n_gpu >= 2:
        max_memory[1] = "0GiB"

    log.info(
        "Loading bf16 from %s (single-GPU + CPU offload, attn=%s, gpu0_max=%s, cpu_max=%s)",
        MODEL_DIR, ATTN_IMPLEMENTATION, GPU0_MAX_MEMORY, CPU_MAX_MEMORY,
    )
    load_kwargs = dict(
        dtype=torch.bfloat16,
        device_map="auto",
        max_memory=max_memory,
        low_cpu_mem_usage=True,
        **extra,
    )
    m = AutoModelForCausalLM.from_pretrained(MODEL_DIR, **load_kwargs)
    return m, "bf16"


@asynccontextmanager
async def lifespan(app: FastAPI):
    global tokenizer, model, model_id, _infer_device, _quant_mode, _eos_ids
    log.info("Loading tokenizer from %s", MODEL_DIR)
    try:
        tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR, use_fast=True)
    except Exception as exc:
        log.warning("Fast tokenizer failed (%s); using slow", exc)
        tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR, use_fast=False)

    if tokenizer.pad_token_id is None and tokenizer.eos_token_id is not None:
        tokenizer.pad_token_id = tokenizer.eos_token_id

    model, _quant_mode = _load_model()
    model.eval()
    model_id = os.path.basename(MODEL_DIR.rstrip("/"))

    try:
        _infer_device = next(p.device for p in model.parameters() if p.device.type == "cuda")
    except StopIteration:
        _infer_device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")

    # Gemma4: stop at <turn|> (end of turn). Token 50 (<|tool_response>) under
    # greedy can fire on the very first step and produce empty output, so we
    # explicitly use <turn|> + <eos>.
    turn_id = tokenizer.convert_tokens_to_ids("<turn|>")
    eos_int = tokenizer.eos_token_id
    _eos_ids = []
    if isinstance(turn_id, int) and turn_id != tokenizer.unk_token_id:
        _eos_ids.append(int(turn_id))
    if isinstance(eos_int, int) and eos_int not in _eos_ids:
        _eos_ids.append(int(eos_int))

    gpu_devs = sorted({str(p.device) for p in model.parameters() if p.device.type == "cuda"})
    cpu_params = sum(1 for p in model.parameters() if p.device.type == "cpu")
    meta_params = sum(1 for p in model.parameters() if p.device.type == "meta")
    log.info(
        "Ready: %s | quant=%s | gpus=%s | infer=%s | eos=%s | cpu_params=%d | meta_params=%d",
        model_id, _quant_mode, gpu_devs, _infer_device, _eos_ids, cpu_params, meta_params,
    )
    yield
    log.info("Shutting down.")


app = FastAPI(lifespan=lifespan)


# ── Schemas ────────────────────────────────────────────────────────────────────

class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    model: Optional[str] = None
    messages: list[Message]
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    stream: Optional[bool] = False


# ── Endpoints ──────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {
        "status": "ok" if model is not None else "loading",
        "model": model_id,
        "quant": _quant_mode,
    }


@app.get("/v1/models")
def list_models():
    return {
        "object": "list",
        "data": [{
            "id": model_id,
            "object": "model",
            "created": int(time.time()),
            "owned_by": "local",
        }]
    }


@app.post("/v1/chat/completions")
async def chat_completions(req: ChatRequest):
    if model is None or tokenizer is None:
        raise HTTPException(503, "Model not loaded yet")

    max_tokens = req.max_tokens or MAX_NEW_TOKENS
    temperature = req.temperature if req.temperature is not None else TEMPERATURE

    chat = [{"role": m.role, "content": m.content} for m in req.messages]
    try:
        # enable_thinking=False asks the chat template (when supported) to skip
        # the model's "thought" channel so reasoning capacity is spent on the
        # actual answer.
        inputs = tokenizer.apply_chat_template(
            chat,
            add_generation_prompt=True,
            return_tensors="pt",
            return_dict=True,
            enable_thinking=False,
        )
    except TypeError:
        inputs = tokenizer.apply_chat_template(
            chat,
            add_generation_prompt=True,
            return_tensors="pt",
            return_dict=True,
        )
    except Exception as e:
        raise HTTPException(400, f"Chat template error: {e}")

    gen_in = {
        k: v.to(_infer_device)
        for k, v in inputs.items()
        if isinstance(v, torch.Tensor)
    }
    if "input_ids" not in gen_in:
        raise HTTPException(500, "Tokenizer produced no input_ids")

    if gen_in["input_ids"].shape[-1] > MAX_PROMPT_TOKENS:
        for k in list(gen_in.keys()):
            t = gen_in[k]
            if isinstance(t, torch.Tensor) and t.dim() >= 2:
                gen_in[k] = t[:, -MAX_PROMPT_TOKENS:]
        log.warning("Prompt truncated to last %d tokens", MAX_PROMPT_TOKENS)
    input_len = gen_in["input_ids"].shape[-1]

    pad_id = tokenizer.pad_token_id or tokenizer.eos_token_id
    do_sample = bool(temperature and temperature > 0)
    gen_kwargs = dict(
        max_new_tokens=max_tokens,
        do_sample=do_sample,
        pad_token_id=pad_id,
    )
    if REPETITION_PENALTY and REPETITION_PENALTY != 1.0:
        gen_kwargs["repetition_penalty"] = REPETITION_PENALTY
    if _eos_ids:
        gen_kwargs["eos_token_id"] = _eos_ids
    if do_sample:
        gen_kwargs["temperature"] = float(temperature)
        if req.top_p is not None:
            gen_kwargs["top_p"] = float(req.top_p)

    t0 = time.time()
    try:
        with torch.no_grad():
            output_ids = model.generate(**gen_in, **gen_kwargs)
    except Exception as e:
        log.exception("Generation failure")
        raise HTTPException(500, f"Generation failed: {e}")
    elapsed = time.time() - t0

    new_tokens = output_ids[0][input_len:]
    raw = tokenizer.decode(new_tokens, skip_special_tokens=False)
    log.info("raw[:240]=%r", raw[:240])
    reply = _clean_gemma4_reply(raw)
    if not reply:
        reply = tokenizer.decode(new_tokens, skip_special_tokens=True).strip()

    prompt_tokens = int(input_len)
    completion_tokens = int(new_tokens.shape[0])
    log.info(
        "Generated %d tokens in %.1fs (%.2f tok/s)",
        completion_tokens, elapsed, completion_tokens / max(elapsed, 1e-3),
    )

    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model_id,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": reply},
            "finish_reason": "stop",
        }],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")
