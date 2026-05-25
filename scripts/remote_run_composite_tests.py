#!/usr/bin/env python3
"""Run composite classic RAG tests on the RunPod pod via SSH (PTY shell)."""
from __future__ import annotations

import os
import re
import sys
import time

import paramiko

HOST = "ssh.runpod.io"
USER = "l8lnmi6ofx0tpz-64411278"
KEY = os.path.expanduser("~/.ssh/id_ed25519")
ANSI_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

REMOTE = r"""
cd /workspace/gemma-test
python3 scripts/test_conversation_intent.py
export USER_PASSWORD=$(grep -E '^USER_SITE_PASSWORD=' .env | head -1 | cut -d= -f2- | tr -d '\r' | tr -d '"' | tr -d "'")
python3 scripts/test_classic_rag_composite.py --live
echo REMOTE_DONE
""".strip()


def safe_print(text: str) -> None:
    clean = ANSI_RE.sub("", text)
    sys.stdout.write(clean.encode("ascii", "replace").decode())
    sys.stdout.flush()


def main() -> int:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        HOST,
        username=USER,
        key_filename=KEY,
        look_for_keys=False,
        allow_agent=False,
        timeout=120,
    )
    shell = client.invoke_shell(term="xterm", width=220, height=60)
    shell.settimeout(0.5)
    time.sleep(3)
    while shell.recv_ready():
        shell.recv(8192)

    shell.send(REMOTE + "\r")
    end = time.time() + 900
    buf = ""
    while time.time() < end:
        try:
            if shell.recv_ready():
                chunk = shell.recv(16384).decode("utf-8", "replace")
                buf += chunk
                safe_print(chunk)
                if "REMOTE_DONE" in buf:
                    break
            else:
                time.sleep(0.3)
        except Exception:
            time.sleep(0.3)

    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
