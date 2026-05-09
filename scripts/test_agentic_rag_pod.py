#!/usr/bin/env python3
"""
Pod / integration tests for agentic RAG + Gemma 4 tool calling.

Run on the GPU pod (or with SSH tunnels to :8000 and :8002):

  cd /workspace/gemma-test   # or your clone path
  python scripts/bootstrap_agentic_map.py
  export AGENTIC_RAG_ENABLED=true
  # restart API if needed so it picks up .env
  python scripts/test_agentic_rag_pod.py

Environment (optional overrides):
  VLLM_BASE_URL=http://127.0.0.1:8002
  API_BASE_URL=http://127.0.0.1:8000
  ADMIN_PASSWORD=...       # admin site password (for /chat agentic_rag)
  USER_PASSWORD=...        # user password (for 403 edge case)
  TEST_CATEGORY=procedures
  TEST_MODEL=gemma4-26b-it
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Any

import httpx

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


def _fail(name: str, detail: str) -> None:
    print(f"FAIL  {name}\n      {detail}")


def _ok(name: str, extra: str = "") -> None:
    print(f"OK    {name}" + (f"  {extra}" if extra else ""))


def test_vllm_health(client: httpx.Client) -> bool:
    try:
        r = client.get("/health", timeout=10.0)
        if r.status_code != 200:
            _fail("vllm_health", f"status {r.status_code}")
            return False
        _ok("vllm_health")
        return True
    except Exception as exc:
        _fail("vllm_health", str(exc))
        return False


def test_vllm_models(client: httpx.Client, model: str) -> bool:
    try:
        r = client.get("/v1/models", timeout=30.0)
        r.raise_for_status()
        data = r.json()
        ids = [m.get("id") for m in data.get("data", [])]
        if model not in ids:
            _fail("vllm_models", f"model {model!r} not in {ids}")
            return False
        _ok("vllm_models", f"id={model}")
        return True
    except Exception as exc:
        _fail("vllm_models", str(exc))
        return False


def test_vllm_tool_roundtrip(vllm: httpx.Client, model: str) -> bool:
    """Minimal OpenAI tools call — verifies gemma4_tool_parser + template."""
    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_capital",
                "description": "Return the capital city of a country.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "country": {"type": "string", "description": "Country name"},
                    },
                    "required": ["country"],
                },
            },
        }
    ]
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": "What is the capital of France? Use the tool.",
            }
        ],
        "tools": tools,
        "tool_choice": "auto",
        "max_tokens": 256,
        "temperature": 0.2,
    }
    try:
        t0 = time.perf_counter()
        r = vllm.post("/v1/chat/completions", json=payload, timeout=120.0)
        dt = (time.perf_counter() - t0) * 1000
        r.raise_for_status()
        data = r.json()
        msg = data["choices"][0].get("message") or {}
        tcalls = msg.get("tool_calls") or []
        if not tcalls:
            content = (msg.get("content") or "")[:400]
            _fail(
                "vllm_tool_roundtrip",
                "no tool_calls in response — start vLLM with Gemma 4 tool flags "
                "(see scripts/start_vllm.sh: VLLM_GEMMA4_TOOLING). "
                f"assistant_content_preview={content!r}",
            )
            return False
        fn = (tcalls[0].get("function") or {})
        if fn.get("name") != "get_capital":
            _fail("vllm_tool_roundtrip", f"unexpected tool {fn.get('name')!r}")
            return False
        _ok("vllm_tool_roundtrip", f"latency_ms≈{dt:.0f} tool={fn.get('name')!r}")
        return True
    except Exception as exc:
        _fail("vllm_tool_roundtrip", str(exc))
        return False


def login(api: httpx.Client, password: str) -> bool:
    r = api.post("/auth/login", json={"password": password})
    return r.status_code == 200


def chat_agentic(
    api: httpx.Client,
    *,
    message: str,
    category: str,
    agentic_rag: bool,
) -> tuple[int, dict[str, Any]]:
    body = {
        "message": message,
        "category": category,
        "agentic_rag": agentic_rag,
        "conversation_history": [],
    }
    t0 = time.perf_counter()
    r = api.post("/chat", json=body, timeout=300.0)
    dt = (time.perf_counter() - t0) * 1000
    try:
        data = r.json()
    except Exception:
        data = {"raw": (r.text or "")[:500]}
    data["_latency_ms"] = round(dt, 1)
    return r.status_code, data


def main() -> int:
    vllm_url = os.environ.get("VLLM_BASE_URL", "http://127.0.0.1:8002").rstrip("/")
    api_url = os.environ.get("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    model = os.environ.get("TEST_MODEL", "gemma4-26b-it")
    category = os.environ.get("TEST_CATEGORY", "procedures")
    admin_pw = os.environ.get("ADMIN_PASSWORD", "")
    user_pw = os.environ.get("USER_PASSWORD", "")

    print("=== agentic RAG pod tests ===")
    print(f"vllm={vllm_url} api={api_url} model={model} category={category}")

    failed = 0

    with httpx.Client(base_url=vllm_url, timeout=httpx.Timeout(300.0)) as vllm:
        if not test_vllm_health(vllm):
            failed += 1
            print("Aborting: vLLM not reachable.")
            return 1
        if not test_vllm_models(vllm, model):
            failed += 1
        if not test_vllm_tool_roundtrip(vllm, model):
            failed += 1

    with httpx.Client(base_url=api_url, timeout=httpx.Timeout(300.0), follow_redirects=True) as api:
        # Edge: agentic without login
        sc, _ = chat_agentic(
            api, message="test", category=category, agentic_rag=True
        )
        if sc != 401:
            _fail("chat_agentic_unauth", f"expected 401, got {sc}")
            failed += 1
        else:
            _ok("chat_agentic_unauth", "401 as expected")

        if not admin_pw:
            print("SKIP  api_agentic_e2e (set ADMIN_PASSWORD)")
            print("SKIP  api_agentic_user_forbidden (set ADMIN_PASSWORD and USER_PASSWORD)")
            return 1 if failed else 0

        api.cookies.clear()
        if not login(api, admin_pw):
            _fail("admin_login", "POST /auth/login failed")
            return 1
        _ok("admin_login")

        sc, data = chat_agentic(
            api,
            message="Comment modifier les coordonnées client pendant une livraison ? Réponds avec les étapes.",
            category=category,
            agentic_rag=True,
        )
        if sc != 200:
            _fail("api_agentic_e2e", f"status {sc} body={data}")
            failed += 1
        else:
            rag = (data.get("metadata") or {}).get("rag") or {}
            tr = rag.get("tool_rounds", "?")
            fc = rag.get("fetch_count", "?")
            lat = data.get("_latency_ms", "?")
            resp_len = len((data.get("response") or ""))
            if rag.get("mode") != "agentic_rag":
                _fail("api_agentic_e2e", f"metadata.rag.mode={rag.get('mode')!r}")
                failed += 1
            elif int(rag.get("tool_rounds") or 0) < 1:
                _fail(
                    "api_agentic_e2e",
                    f"tool_rounds={rag.get('tool_rounds')!r} (no tool_calls — check vLLM Gemma 4 flags)",
                )
                failed += 1
            elif int(rag.get("fetch_count") or 0) < 1:
                _fail(
                    "api_agentic_e2e",
                    f"fetch_count={rag.get('fetch_count')!r} (expected fetch_procedure after search_map)",
                )
                failed += 1
            else:
                _ok(
                    "api_agentic_e2e",
                    f"latency_ms={lat} tool_rounds={tr} fetch_count={fc} response_chars={resp_len}",
                )
            reasons = rag.get("vllm_finish_reasons")
            if reasons:
                print(f"      vllm_finish_reasons={reasons}")

        # Darija-shaped query (still French procedure KB)
        sc2, data2 = chat_agentic(
            api,
            message="كيفاش نبدل الرقم ديال الزبون إلا كان الكولي فالليفريزون؟",
            category=category,
            agentic_rag=True,
        )
        if sc2 != 200:
            _fail("api_agentic_darija", f"status {sc2}")
            failed += 1
        else:
            _ok(
                "api_agentic_darija",
                f"latency_ms={data2.get('_latency_ms')} chars={len(data2.get('response') or '')}",
            )

        # Wrong procedure id simulation: model might fetch bad id — we only check HTTP OK
        sc3, data3 = chat_agentic(
            api,
            message="Procédure interne XYZNONEXISTENT999 pour test refus.",
            category=category,
            agentic_rag=True,
        )
        if sc3 != 200:
            _fail("api_agentic_obscure", f"status {sc3}")
            failed += 1
        else:
            _ok("api_agentic_obscure", f"latency_ms={data3.get('_latency_ms')}")

        if user_pw:
            api.cookies.clear()
            if login(api, user_pw):
                sc4, _ = chat_agentic(
                    api,
                    message="test",
                    category=category,
                    agentic_rag=True,
                )
                # If AGENTIC_RAG_ALLOW_NON_ADMIN=false expect 403
                if sc4 == 403:
                    _ok("api_agentic_user_forbidden", "403 as expected")
                elif sc4 == 200:
                    _ok(
                        "api_agentic_user_forbidden",
                        "200 — AGENTIC_RAG_ALLOW_NON_ADMIN may be true",
                    )
                else:
                    _fail("api_agentic_user_forbidden", f"unexpected {sc4}")

    print(f"\nDone. failures={failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
