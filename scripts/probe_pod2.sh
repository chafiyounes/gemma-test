#!/usr/bin/env bash
set -u
echo '== nvidia-smi header =='
nvidia-smi | head -4 || true
echo '== torch versions =='
pip index versions torch 2>&1 | head -3 || true
echo '== current torch cuda =='
python3 -c 'import torch; print("torch", torch.__version__, "cuda", torch.version.cuda)'
