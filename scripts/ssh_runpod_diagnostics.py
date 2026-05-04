#!/usr/bin/env python3
"""SSH diagnostics for RunPod pods — configurable and safe to run locally.

Usage:
  python3 scripts/ssh_runpod_diagnostics.py --host ssh.runpod.io --user <user> --key ~/.ssh/id_ed25519

This connects via SSH, runs GPU and vLLM checks, and prints collected output.
"""
import argparse
import paramiko
import time
import re
import os
import sys

PROMPT_RE = re.compile(r"[#$]\s*$")


def recv(shell, timeout=30):
    buf = b""
    t = time.time() + timeout
    while time.time() < t:
        if shell.recv_ready():
            buf += shell.recv(8192)
        else:
            time.sleep(0.1)
    try:
        return buf.decode("utf-8", "replace")
    except Exception:
        return str(buf)


def run_checks(host, user, key_path, port=22, timeout=30):
    key_path = os.path.expanduser(key_path)
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"Connecting to {user}@{host} using key {key_path}...")
    client.connect(host, username=user, key_filename=key_path, timeout=timeout, look_for_keys=False, allow_agent=False)
    shell = client.invoke_shell(term="xterm-256color", width=220, height=50)
    shell.settimeout(timeout)
    time.sleep(1.5)
    shell.recv(20000)

    cmds = [
        ("nvidia-smi", "nvidia-smi --query-gpu=index,name,memory.total,memory.used,memory.free --format=csv,noheader"),
        ("cuda device count", "python3 -c 'import torch; n=torch.cuda.device_count(); print(\"CUDA devices:\", n); [print(i, torch.cuda.get_device_properties(i).name, torch.cuda.get_device_properties(i).total_memory//1024//1024, \"MB total\") for i in range(n)]'"),
        ("vLLM tail (last 50)", "tail -50 /workspace/gemma-test/logs/vllm_*.log 2>/dev/null || echo 'no vllm logs'"),
        ("api tail (last 50)", "tail -50 /workspace/gemma-test/logs/api.log 2>/dev/null || echo 'no api log'"),
        ("bitsandbytes", "python3 -c 'import importlib,sys; print(importlib.util.find_spec(\"bitsandbytes\") is not None and \"INSTALLED\" or \"NOT INSTALLED\")'"),
        ("free memory per gpu", "python3 -c 'import torch; [print(f\"cuda:{i} free: {torch.cuda.mem_get_info(i)[0]//1024//1024} MB / {torch.cuda.mem_get_info(i)[1]//1024//1024} MB\") for i in range(torch.cuda.device_count())]'"),
        ("vLLM health", "curl -sS -m 5 http://localhost:8002/health || echo 'vllm-unreachable'"),
        ("API health", "curl -sS -m 5 http://localhost:8000/health || echo 'api-unreachable'"),
        ("quick inference", 'curl -s -m 120 -X POST http://localhost:8002/v1/chat/completions -H "Content-Type: application/json" -d "{\"model\":\"gemma4-26b-it\",\"messages\":[{\"role\":\"user\",\"content\":\"Hello\"}],\"max_tokens\":20}" || echo INFERENCE-FAILED')
    ]

    for label, cmd in cmds:
        print("\n" + "=" * 60)
        print(f">>> {label}\n{cmd}\n")
        shell.send(cmd + "\n")
        # give the command some time for output
        time.sleep(2)
        out = recv(shell, timeout=10)
        print(out)

    shell.close()
    client.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=False, default=os.environ.get("RUNPOD_HOST", "ssh.runpod.io"))
    parser.add_argument("--user", required=False, default=os.environ.get("RUNPOD_USER"))
    parser.add_argument("--key", required=False, default=os.environ.get("RUNPOD_KEY", "~/.ssh/id_ed25519"))
    args = parser.parse_args()

    if not args.user:
        print("Error: --user required (or set RUNPOD_USER env var)")
        sys.exit(2)

    run_checks(args.host, args.user, args.key)


if __name__ == "__main__":
    main()
