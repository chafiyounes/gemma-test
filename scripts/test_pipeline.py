#!/usr/bin/env python3
"""
Test script to validate the full Gemma pipeline:
1. Test GPU visibility
2. Test inference server health
3. Test API health
4. Test authentication
5. Test document loading (all 10 procedures)
6. Test chat with procedure-based prompts
"""
import asyncio
import json
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx

API_URL = os.environ.get("API_URL", "http://localhost:8000")
VLLM_URL = os.environ.get("VLLM_URL", "http://localhost:8002")
USER_PASSWORD = os.environ.get("USER_PASSWORD", "user1234")

PASS = "✅"
FAIL = "❌"
WARN = "⚠️"


async def test_gpu_visibility():
    """Test 1: Check GPU visibility via inference server."""
    print("\n═══ Test 1: GPU Visibility ═══")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{VLLM_URL}/health")
            if resp.status_code == 200:
                data = resp.json()
                print(f"  {PASS} Inference server is running — model: {data.get('model', '?')}")
                return True
            else:
                print(f"  {FAIL} Inference server returned {resp.status_code}")
                return False
    except Exception as e:
        print(f"  {FAIL} Cannot reach inference server at {VLLM_URL}: {e}")
        return False


async def test_api_health():
    """Test 2: Check FastAPI backend health."""
    print("\n═══ Test 2: API Health ═══")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{API_URL}/health")
            if resp.status_code == 200:
                data = resp.json()
                print(f"  {PASS} API is running — status: {data.get('status')}")
                print(f"       model_available: {data.get('model_available')}")
                print(f"       model_name: {data.get('model_name')}")
                print(f"       vllm_url: {data.get('vllm_url')}")
                return True
            else:
                print(f"  {FAIL} API returned {resp.status_code}")
                return False
    except Exception as e:
        print(f"  {FAIL} Cannot reach API at {API_URL}: {e}")
        return False


async def test_auth():
    """Test 3: Authentication flow."""
    print("\n═══ Test 3: Authentication ═══")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            # Login
            resp = await client.post(
                f"{API_URL}/auth/login",
                json={"password": USER_PASSWORD},
            )
            if resp.status_code != 200:
                print(f"  {FAIL} Login failed with status {resp.status_code}")
                return None
            data = resp.json()
            print(f"  {PASS} Login successful — role: {data.get('role')}")

            # Extract session cookie
            cookies = dict(resp.cookies)
            print(f"       Session cookie set: {'gemma_session' in str(cookies) or len(cookies) > 0}")

            # Check session
            resp2 = await client.get(f"{API_URL}/auth/session", cookies=resp.cookies)
            if resp2.status_code == 200:
                session = resp2.json()
                print(f"  {PASS} Session check — authenticated: {session.get('authenticated')}")
            else:
                print(f"  {WARN} Session check returned {resp2.status_code}")

            return resp.cookies
    except Exception as e:
        print(f"  {FAIL} Auth error: {e}")
        return None


async def test_categories(cookies):
    """Test 4: Document categories."""
    print("\n═══ Test 4: Document Categories ═══")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{API_URL}/categories", cookies=cookies)
            if resp.status_code == 200:
                data = resp.json()
                cats = data.get("categories", [])
                print(f"  {PASS} Found {len(cats)} categories:")
                for cat in cats:
                    print(f"       • {cat['name']}: {cat['doc_count']} docs → {cat.get('doc_names', [])}")
                return True
            else:
                print(f"  {FAIL} Categories returned {resp.status_code}: {resp.text}")
                return False
    except Exception as e:
        print(f"  {FAIL} Categories error: {e}")
        return False


async def test_chat(cookies, message, label=""):
    """Test 5+: Send a chat message."""
    prefix = f" ({label})" if label else ""
    print(f"\n═══ Test: Chat{prefix} ═══")
    print(f"  → Message: {message[:80]}{'...' if len(message) > 80 else ''}")
    try:
        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.post(
                f"{API_URL}/chat",
                json={
                    "message": message,
                    "user_id": "test-script",
                    "session_id": "test-session",
                    "conversation_history": [],
                    "category": "procedures",
                },
                cookies=cookies,
            )
            if resp.status_code == 200:
                data = resp.json()
                response_text = data.get("response", "")
                model = data.get("model", "?")
                interaction_id = data.get("interaction_id", "?")
                print(f"  {PASS} Response received (model: {model}, id: {interaction_id[:8]}...)")
                # Print the first 300 chars of the response
                preview = response_text[:300] + ("..." if len(response_text) > 300 else "")
                print(f"  ← Response: {preview}")
                return True
            else:
                print(f"  {FAIL} Chat returned {resp.status_code}: {resp.text[:200]}")
                return False
    except Exception as e:
        print(f"  {FAIL} Chat error: {e}")
        return False


async def main():
    print("╔══════════════════════════════════════════════════╗")
    print("║  Gemma Test — Full Pipeline Validation           ║")
    print(f"║  API: {API_URL:<40s}   ║")
    print(f"║  VLLM: {VLLM_URL:<39s}   ║")
    print("╚══════════════════════════════════════════════════╝")

    results = {}

    # 1. GPU check via inference server
    results["gpu"] = await test_gpu_visibility()

    # 2. API health
    results["api"] = await test_api_health()

    if not results["api"]:
        print(f"\n{FAIL} API is not running — skipping remaining tests")
        return

    # 3. Auth
    cookies = await test_auth()
    results["auth"] = cookies is not None

    if not results["auth"]:
        print(f"\n{FAIL} Auth failed — skipping remaining tests")
        return

    # 4. Categories
    results["categories"] = await test_categories(cookies)

    # 5. Chat tests — procedure-based prompts
    test_prompts = [
        ("Procédure produits interdits",
         "Quels sont les produits interdits à l'envoi chez SENDIT ?"),

        ("Gestion colis endommagé",
         "Quelle est la procédure quand un colis est endommagé ?"),

        ("Demande de remboursement",
         "Comment faire une demande de remboursement pour un colis endommagé ?"),

        ("Darija test",
         "كيفاش نقدر نتبع الكولي ديالي؟"),

        ("Ville de ramassage",
         "Comment ajouter une ville de ramassage ?"),
    ]

    chat_results = []
    for label, prompt in test_prompts:
        ok = await test_chat(cookies, prompt, label)
        chat_results.append(ok)

    results["chat"] = all(chat_results)

    # Summary
    print("\n" + "═" * 50)
    print("  SUMMARY")
    print("═" * 50)
    for key, passed in results.items():
        icon = PASS if passed else FAIL
        print(f"  {icon} {key}")

    total = len(results)
    passed = sum(1 for v in results.values() if v)
    print(f"\n  {passed}/{total} tests passed")

    if passed == total:
        print(f"\n  🎉 All tests passed!")
    else:
        print(f"\n  {FAIL} Some tests failed — check output above")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
