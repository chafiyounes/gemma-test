#!/usr/bin/env python3
"""Quick RunPod health diagnostic via SSH."""
import os
import re
import sys
import time

import paramiko

HOST = "ssh.runpod.io"
USER = "l8lnmi6ofx0tpz-64411278"
KEY_PATH = os.path.expanduser("~/.ssh/id_ed25519")
ANSI_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

CMDS = [
    "cd /workspace/gemma-test",
    "tmux ls 2>&1 || true",
    "curl -s -o /dev/null -w 'health:%{http_code}' http://127.0.0.1:8000/health || echo curl_failed",
    "curl -s -o /dev/null -w 'vllm:%{http_code}' http://127.0.0.1:8002/v1/models || echo vllm_failed",
    "ps aux | grep uvicorn | grep -v grep | head -5",
    "tmux capture-pane -t gemma-test:api -p -S -120 2>&1 | tail -50",
]


def main() -> int:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"Connecting to {USER}@{HOST}...")
    client.connect(
        HOST,
        username=USER,
        key_filename=KEY_PATH,
        look_for_keys=False,
        allow_agent=False,
    )
    shell = client.invoke_shell(term="xterm", width=220, height=60)
    shell.settimeout(1.0)
    time.sleep(3)
    while shell.recv_ready():
        shell.recv(8192)

    for cmd in CMDS:
        print(f"\n>>> {cmd}")
        shell.send(cmd + "\r")
        end = time.time() + 60
        full = ""
        while time.time() < end:
            try:
                if shell.recv_ready():
                    chunk = shell.recv(8192).decode("utf-8", "replace")
                    full += chunk
                    clean = ANSI_RE.sub("", chunk)
                    sys.stdout.write(clean.encode("ascii", "replace").decode())
                    sys.stdout.flush()
                    lines = ANSI_RE.sub("", full).splitlines()
                    if lines:
                        last = lines[-1].strip()
                        if (last.endswith("#") or last.endswith("$")) and cmd[:10] not in last:
                            break
                else:
                    time.sleep(0.4)
            except Exception:
                time.sleep(0.4)

    shell.close()
    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
