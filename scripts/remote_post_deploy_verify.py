#!/usr/bin/env python3
"""After git deploy: pip deps, agentic map+index, API restart, pod tests + sample chats.

Usage (from dev machine, SSH key to RunPod):
  python scripts/remote_post_deploy_verify.py

Runs ``scripts/pod_verify_remote.sh`` on the pod (must exist at repo path after git pull).
"""
from __future__ import annotations

import os
import re
import sys

import paramiko

HOST = "ssh.runpod.io"
USER = "l8lnmi6ofx0tpz-64411278"
KEY = os.path.expanduser(r"~/.ssh/id_ed25519")
ANSI = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def main() -> int:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            HOST,
            username=USER,
            key_filename=KEY,
            look_for_keys=False,
            allow_agent=False,
            timeout=120,
        )
    except Exception as exc:
        print("CONNECT_FAIL", exc, file=sys.stderr)
        return 2

    shell = client.invoke_shell(term="xterm", width=200, height=60)
    shell.settimeout(0.4)
    import time

    time.sleep(2.0)
    while shell.recv_ready():
        shell.recv(65536)

    shell.send("bash /workspace/gemma-test/scripts/pod_verify_remote.sh\n")

    deadline = time.time() + 3600.0
    buf = ""
    while time.time() < deadline:
        try:
            if shell.recv_ready():
                chunk = shell.recv(65536).decode("utf-8", "replace")
                buf += chunk
                sys.stdout.write(ANSI.sub("", chunk))
                sys.stdout.flush()
                if "VERIFY_DONE" in buf:
                    break
            else:
                time.sleep(0.4)
        except (EOFError, TimeoutError):
            time.sleep(0.4)

    shell.close()
    client.close()

    plain = ANSI.sub("", buf)
    if "vllm_tool_roundtrip" in plain and "FAIL" in plain:
        print(
            "\n[NOTE] vLLM tool test failed — restart vLLM with Gemma 4 tooling:\n"
            "  cd /workspace/gemma-test && bash start_all.sh gemma4\n",
            file=sys.stderr,
        )
    if "VERIFY_DONE" not in plain:
        print("VERIFY_INCOMPLETE (script may still be running or path wrong)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
