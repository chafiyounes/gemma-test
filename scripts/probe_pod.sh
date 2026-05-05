#!/usr/bin/env bash
# Quick probe of pod stack state.
set -u
echo '== bnb versions =='
pip index versions bitsandbytes 2>&1 | head -5 || true
echo '== accelerate versions =='
pip index versions accelerate 2>&1 | head -5 || true
echo '== transformers versions =='
pip index versions transformers 2>&1 | head -5 || true
echo '== torch features =='
python3 - <<'PY'
import torch, sys
print("torch", torch.__version__)
print("has set_submodule on nn.Module:", hasattr(torch.nn.Module, "set_submodule"))
print("cuda available:", torch.cuda.is_available(), "n_gpu:", torch.cuda.device_count())
PY
echo '== model class probe =='
python3 - <<'PY'
from transformers import AutoConfig
c = AutoConfig.from_pretrained('/workspace/models/gemma4-26b-it')
print("config class:", type(c).__name__)
print("architectures:", getattr(c, "architectures", None))
print("model_type:", c.model_type)
PY
