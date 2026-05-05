#!/usr/bin/env bash
set -u
python3 - <<'PY'
import json, os
idx_path = '/workspace/models/gemma4-26b-it/model.safetensors.index.json'
with open(idx_path) as f:
    idx = json.load(f)
keys = list(idx['weight_map'].keys())
print(f"total keys: {len(keys)}")
print("prefixes seen:")
prefixes = sorted({k.split('.')[0] for k in keys})
for p in prefixes:
    cnt = sum(1 for k in keys if k.startswith(p + '.') or k == p)
    print(f"  {p:30s}  {cnt:5d}")
print()
print("first 10 keys:")
for k in keys[:10]:
    print(f"  {k}")
print()
print("first 5 lm_head / language_model keys:")
for k in keys:
    if 'lm_head' in k or 'language_model' in k:
        print(f"  {k}")
        # break after 6 of these
PY
