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
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

MODEL_DIR = os.environ.get("MODEL_DIR", "/workspace/models/gemma4-26b-it")
MAX_NEW_TOKENS = int(os.environ.get("MAX_NEW_TOKENS", "1024"))
TEMPERATURE = float(os.environ.get("TEMPERATURE", "0.7"))
PORT = int(os.environ.get("PORT", "8002"))
# INT8 quantization via bitsandbytes: halves VRAM usage (~26 GB vs 52 GB for 26B model)
# Set USE_INT8=0 to disable (falls back to bfloat16 with CPU offload)
USE_INT8 = os.environ.get("USE_INT8", "1") == "1"

# Global model state
tokenizer = None
model = None
model_id = None
_infer_device = None  # set after model load


def _load_model():
    """Load model with INT8 quantization if bitsandbytes available, else bfloat16."""
    if USE_INT8:
        try:
            import bitsandbytes  # noqa: F401
            log.info("Loading model in INT8 (bitsandbytes) from %s ...", MODEL_DIR)
            bnb_config = BitsAndBytesConfig(load_in_8bit=True)
            m = AutoModelForCausalLM.from_pretrained(
                MODEL_DIR,
                quantization_config=bnb_config,
                device_map="auto",
            )
            log.info("Model loaded in INT8 — all weights on GPU, zero CPU offload")
            return m, "int8"
        except ImportError:
            log.warning("bitsandbytes not installed — falling back to bfloat16")
        except Exception as exc:
            log.warning("INT8 load failed (%s) — falling back to bfloat16", exc)

    log.info("Loading model in bfloat16 from %s (device_map=auto) ...", MODEL_DIR)
    m = AutoModelForCausalLM.from_pretrained(
        MODEL_DIR,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        low_cpu_mem_usage=True,
    )
    return m, "bf16"


@asynccontextmanager
async def lifespan(app: FastAPI):
    global tokenizer, model, model_id, _infer_device
    log.info("Loading tokenizer from %s ...", MODEL_DIR)
    tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR)
    model, quant_mode = _load_model()
    model.eval()
    model_id = os.path.basename(MODEL_DIR)
    # Determine primary inference device (first GPU parameter)
    try:
        _infer_device = next(p.device for p in model.parameters() if p.device.type == 'cuda')
    except StopIteration:
        _infer_device = torch.device('cuda:0' if torch.cuda.is_available() else 'cpu')
    gpu_devices = list(set(str(p.device) for p in model.parameters() if p.device.type == 'cuda'))
    meta_params = sum(1 for p in model.parameters() if p.device.type == 'meta')
    log.info("Model ready: %s  |  quant=%s  |  gpu_devices=%s  |  infer_device=%s  |  meta_params=%d",
             model_id, quant_mode, gpu_devices, _infer_device, meta_params)
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
