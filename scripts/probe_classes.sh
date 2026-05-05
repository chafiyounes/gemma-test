#!/usr/bin/env bash
set -u
python3 - <<'PY'
import transformers as t
print("transformers", t.__version__)
classes = [n for n in dir(t) if "gemma4" in n.lower() or "Gemma4" in n]
print("Gemma4* classes:")
for c in classes:
    print(" ", c)
print()
try:
    from transformers import Gemma4ForCausalLM
    print("Gemma4ForCausalLM importable: YES")
except Exception as e:
    print("Gemma4ForCausalLM:", type(e).__name__, e)
try:
    from transformers import Gemma4TextModel
    print("Gemma4TextModel importable: YES")
except Exception as e:
    print("Gemma4TextModel:", type(e).__name__, e)
try:
    from transformers.models.gemma4 import modeling_gemma4 as m
    print("modeling_gemma4 module:", m.__file__)
    syms = [n for n in dir(m) if not n.startswith("_")]
    print("symbols:", [s for s in syms if "Gemma4" in s])
except Exception as e:
    print("modeling_gemma4:", type(e).__name__, e)
PY
