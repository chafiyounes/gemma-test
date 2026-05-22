#!/usr/bin/env python3
"""Diagnose pod health via RunPod SSH (PTY shell)."""
import os
import re
import sys
import time

import paramiko

HOST = "ssh.runpod.io"
USER = "l8lnmi6ofx0tpz-64411278"
KEY_PATH = os.path.expanduser("~/.ssh/id_ed25519")
ANSI_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def safe_print(text):
    clean = ANSI_RE.sub("", text)
    sys.stdout.write(clean.encode("ascii", "replace").decode())
    sys.stdout.flush()


def run_shell(cmds):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"Connecting to {USER}@{HOST}...")
    client.connect(HOST, username=USER, key_filename=KEY_PATH, look_for_keys=False, allow_agent=False)
    shell = client.invoke_shell(term="xterm", width=220, height=60)
    shell.settimeout(0.5)
    time.sleep(3)
    while shell.recv_ready():
        shell.recv(8192)

    for cmd in cmds:
        print(f"\n>>> {cmd}\n")
        shell.send(cmd + "\r")
        end = time.time() + 45
        buf = ""
        while time.time() < end:
            try:
                if shell.recv_ready():
                    chunk = shell.recv(16384).decode("utf-8", "replace")
                    buf += chunk
                    safe_print(chunk)
                    clean = ANSI_RE.sub("", buf)
                    lines = clean.splitlines()
                    if lines:
                        last = lines[-1].strip()
                        if (last.endswith("#") or last.endswith("$")) and cmd[:12] not in last:
                            break
                else:
                    time.sleep(0.4)
            except Exception as exc:
                print(f"[WARN] {exc}")
                break

    shell.close()
    client.close()


if __name__ == "__main__":
    run_shell(
        [
            "cd /workspace/gemma-test",
            "echo '=== tmux ===' && tmux ls 2>&1 || true",
            "echo '=== ports ===' && ss -tlnp 2>/dev/null | grep -E ':8000|:8002' || netstat -tlnp 2>/dev/null | grep -E ':8000|:8002' || true",
            "echo '=== curl vllm ===' && curl -s -m 5 -w '\\nHTTP:%{http_code}\\n' http://127.0.0.1:8002/health 2>&1 || true",
            "echo '=== curl api ===' && curl -s -m 5 -w '\\nHTTP:%{http_code}\\n' http://127.0.0.1:8000/health 2>&1 || true",
            "echo '=== api.log tail ===' && tail -60 logs/api.log 2>&1 || true",
            "echo '=== vllm.log tail ===' && tail -40 logs/vllm.log 2>&1 || true",
            "echo '=== python import api ===' && cd /workspace/gemma-test && python3 -c 'import api.main' 2>&1 || true",
            "echo '=== vllm processes ===' && ps aux | grep -E 'vllm|uvicorn' | grep -v grep || true",
            "echo '=== nvidia-smi ===' && nvidia-smi --query-gpu=index,memory.used,memory.total,utilization.gpu --format=csv 2>&1 || true",
            "echo '=== vllm.log wc ===' && wc -l logs/vllm.log 2>&1 && tail -15 logs/vllm.log 2>&1 || true",
            "echo '=== vllm_gemma4.log ===' && tail -30 logs/vllm_gemma4.log 2>&1 || true",
            "echo '=== worker pids ===' && ps -p 52681,52682,52506 -o pid,stat,etime,cmd 2>&1 || true",
        ]
    )
