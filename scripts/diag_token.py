#!/usr/bin/env python3
from transformers import AutoTokenizer
t = AutoTokenizer.from_pretrained("/workspace/models/gemma4-26b-it")
print("id 0   ->", repr(t.decode([0])))
print("id 1   ->", repr(t.decode([1])))
print("id 50  ->", repr(t.decode([50])))
print("id 106 ->", repr(t.decode([106])))
print("eos_token =", t.eos_token, "id =", t.eos_token_id)
print("pad_token =", t.pad_token, "id =", t.pad_token_id)
print("special_tokens_map:", t.special_tokens_map)
print()
print("ids 100-110:", [(i, t.decode([i])) for i in range(100, 111)])
print()
print("ids 45-55:", [(i, t.decode([i])) for i in range(45, 56)])
