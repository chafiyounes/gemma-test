#!/usr/bin/env python3
"""Post-deploy verification: vLLM, API, SPA assets, auth, and one /chat round-trip.

Run from repo root after deploy:
  python scripts/verify_full_stack.py
  python scripts/verify_full_stack.py --local   # also check http://127.0.0.1:8000 (SSH tunnel)

Exits 0 only when all checks pass. Uses scripts/runpod_ssh.py for pod access.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import httpx

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.runpod_ssh import HOST, KEY_PATH, USER

import paramiko

ANSI = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def _pod_shell_script() -> str:
    return r"""
set -e
cd /workspace/gemma-test
FAIL=0
ok() { echo "OK $1"; }
bad() { echo "FAIL $1"; FAIL=1; }

test -f web_test/dist/index.html || bad "dist/index.html missing"
curl -sf http://127.0.0.1:8002/health >/dev/null || curl -sf http://127.0.0.1:8002/v1/models >/dev/null || bad "vLLM down"
curl -sf http://127.0.0.1:8000/health >/dev/null || bad "API health down"
CODE=$(curl -sS -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/)
test "$CODE" = "200" || bad "SPA root HTTP $CODE"
JS=$(grep -oE '/assets/index-[^"]+\.js' web_test/dist/index.html | head -1)
test -n "$JS" || bad "main JS bundle not found in index.html"
CODE=$(curl -sS -o /dev/null -w '%{http_code}' "http://127.0.0.1:8000${JS}")
test "$CODE" = "200" || bad "SPA asset HTTP $CODE for $JS"

# E2E chat (credentials from pod .env if present)
USER_PW=$(grep -m1 '^USER_SITE_PASSWORD=' .env 2>/dev/null | cut -d= -f2- || echo user1234)
curl -sf -c /tmp/vf_cookies -X POST http://127.0.0.1:8000/auth/login \
  -H 'Content-Type: application/json' \
  -d "{\"username\":\"user\",\"password\":\"${USER_PW}\"}" >/dev/null || bad "auth/login"
CHAT=$(curl -sf -b /tmp/vf_cookies -X POST http://127.0.0.1:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"Bonjour, test verification deploy.","category":"procedures","conversation_history":[]}' \
  --max-time 300)
echo "$CHAT" | grep -q '"response"' || bad "chat missing response field"
echo "$CHAT" | grep -q '"model_available"' && bad "unexpected" || true
test "$FAIL" -eq 0 && echo VERIFY_STACK_OK || { echo VERIFY_STACK_FAIL; exit 1; }
"""


def run_pod_verify() -> bool:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"Pod checks via {USER}@{HOST} ...")
    client.connect(HOST, username=USER, key_filename=KEY_PATH, look_for_keys=False, allow_agent=False)
    shell = client.invoke_shell(term="xterm", width=200, height=50)
    time.sleep(2)
    while shell.recv_ready():
        shell.recv(8192)
    shell.send(_pod_shell_script() + "\n")
    deadline = time.time() + 360
    buf = ""
    while time.time() < deadline:
        time.sleep(0.5)
        while shell.recv_ready():
            chunk = shell.recv(8192).decode("utf-8", "replace")
            buf += chunk
            print(ANSI.sub("", chunk), end="", flush=True)
        if "VERIFY_STACK_OK" in buf or "VERIFY_STACK_FAIL" in buf:
            break
    shell.close()
    client.close()
    return "VERIFY_STACK_OK" in buf


def run_local_tunnel_check(base: str = "http://127.0.0.1:8000") -> bool:
    print(f"\nLocal tunnel checks ({base}) ...")
    try:
        with httpx.Client(timeout=15.0) as client:
            r = client.get(f"{base}/health")
            r.raise_for_status()
            data = r.json()
            if not data.get("model_available"):
                print("FAIL local: model_available=false")
                return False
            r = client.get(f"{base}/")
            if r.status_code != 200 or "html" not in (r.headers.get("content-type") or "").lower():
                print(f"FAIL local: SPA root status={r.status_code}")
                return False
            print("OK local: health + SPA root")
            return True
    except Exception as exc:
        print(f"FAIL local: {exc}")
        print("  → Start tunnel: ssh -N -L 8000:localhost:8000 -L 8002:localhost:8002 runpod")
        return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--local", action="store_true", help="Also probe http://127.0.0.1:8000")
    parser.add_argument("--skip-pod", action="store_true")
    args = parser.parse_args()

    ok = True
    if not args.skip_pod:
        ok = run_pod_verify() and ok
    if args.local:
        ok = run_local_tunnel_check() and ok
    if ok:
        print("\n=== All stack checks passed ===")
        if not args.local:
            print("Open chat: ssh -N -L 8000:localhost:8000 -L 8002:localhost:8002 runpod")
            print("Then http://localhost:8000")
        return 0
    print("\n=== Stack verification FAILED ===", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
