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

# Global model state
tokenizer = None
model = None
model_id = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global tokenizer, model, model_id
    log.info("Loading tokenizer from %s ...", MODEL_DIR)
    tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR)
    log.info("Loading model from %s with device_map=auto ...", MODEL_DIR)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_DIR,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        low_cpu_mem_usage=True,
    )
    model.eval()
    model_id = os.path.basename(MODEL_DIR)
    log.info("Model loaded: %s  |  devices: %s", model_id, list(set(str(p.device) for p in model.parameters())))
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
        input_ids = tokenizer.apply_chat_template(
            chat,
            add_generation_prompt=True,
            return_tensors="pt",
        )
    except Exception as e:
        raise HTTPException(400, f"Chat template error: {e}")

    input_ids = input_ids.to(model.device)

    t0 = time.time()
    with torch.no_grad():
        output_ids = model.generate(
            input_ids,
            max_new_tokens=max_tokens,
            temperature=temperature,
            do_sample=temperature > 0,
            pad_token_id=tokenizer.eos_token_id,
        )

    # Decode only the new tokens
    new_tokens = output_ids[0][input_ids.shape[-1]:]
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
