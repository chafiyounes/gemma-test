#!/usr/bin/env python3
"""
Minimal OpenAI-compatible chat completions server using HuggingFace transformers.
Serves Gemma 4 across multiple GPUs via device_map='auto'.
Endpoints:
  GET  /health
  GET  /v1/models
  POST /v1/chat/completions
"""
import os, time, json, uuid, logging, asyncio
from typing import Optional
from contextlib import asynccontextmanager

import torch
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from transformers import AutoTokenizer, AutoModelForCausalLM, pipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

MODEL_DIR = os.environ.get("MODEL_DIR", "/workspace/models/gemma4-26b-it")
MAX_NEW_TOKENS = int(os.environ.get("MAX_NEW_TOKENS", "1024"))
TEMPERATURE = float(os.environ.get("TEMPERATURE", "0.7"))
PORT = int(os.environ.get("PORT", "8002"))
# Per-GPU memory cap: default 40 GiB leaves headroom for activations on each A40 (45.4 GiB total)
GPU_MEMORY_PER_DEVICE = os.environ.get("GPU_MEMORY_PER_DEVICE", "40GiB")

# Global model state
tokenizer = None
model = None
model_id = None
_infer_device = None  # set after model load

@asynccontextmanager
async def lifespan(app: FastAPI):
    global tokenizer, model, model_id
    log.info("Loading tokenizer from %s ...", MODEL_DIR)
    tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR)
    global _infer_device
    # Build max_memory map: one entry per visible CUDA device + cpu fallback
    n_gpus = torch.cuda.device_count()
    max_memory = {i: GPU_MEMORY_PER_DEVICE for i in range(n_gpus)}
    max_memory["cpu"] = "60GiB"  # allow CPU as last resort
    log.info("Loading model from %s  |  GPUs visible: %d  |  max_memory: %s", MODEL_DIR, n_gpus, max_memory)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_DIR,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        max_memory=max_memory,
        low_cpu_mem_usage=True,
    )
    model.eval()
    model_id = os.path.basename(MODEL_DIR)
    gpu_devices = [str(p.device) for p in model.parameters() if p.device.type != 'meta']
    cpu_params = sum(1 for p in model.parameters() if p.device.type == 'meta')
    _infer_device = max(set(gpu_devices), key=gpu_devices.count) if gpu_devices else 'cpu'
    log.info("Model loaded: %s  |  devices: %s  |  meta(cpu-offload) params: %d",
             model_id, list(set(gpu_devices)), cpu_params)
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
    stream: Optional[bool] = False


# ── Endpoints ──────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "model": model_id}

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
    if model is None:
        raise HTTPException(503, "Model not loaded yet")

    max_tokens = req.max_tokens or MAX_NEW_TOKENS
    temperature = req.temperature if req.temperature is not None else TEMPERATURE

    # Build prompt using tokenizer's chat template
    chat = [{"role": m.role, "content": m.content} for m in req.messages]
    try:
        inputs = tokenizer.apply_chat_template(
            chat,
            add_generation_prompt=True,
            return_tensors="pt",
            return_dict=True,
        )
    except Exception as e:
        raise HTTPException(400, f"Chat template error: {e}")

    input_ids = inputs["input_ids"].to(_infer_device)
    attention_mask = inputs.get("attention_mask")
    if attention_mask is not None:
        attention_mask = attention_mask.to(_infer_device)
    input_len = input_ids.shape[-1]

    t0 = time.time()
    with torch.no_grad():
        output_ids = model.generate(
            input_ids,
            attention_mask=attention_mask,
            max_new_tokens=max_tokens,
            temperature=temperature,
            do_sample=temperature > 0,
            pad_token_id=tokenizer.eos_token_id,
        )

    # Decode only the new tokens
    new_tokens = output_ids[0][input_len:]
    reply = tokenizer.decode(new_tokens, skip_special_tokens=True).strip()
    elapsed = time.time() - t0
    prompt_tokens = input_ids.shape[-1]
    completion_tokens = len(new_tokens)

    log.info("Generated %d tokens in %.1fs", completion_tokens, elapsed)

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
