"""Upload repo files to the RunPod workspace over SFTP (paramiko).

RunPod's gateway often rejects non-PTY `scp`/one-shot `ssh cmd`; this uses the
same host/key as `pod_cmd.py`.

Usage (from repo root):

  python scripts/push_to_runpod.py core/llm.py app_config/settings.py

Remote root default: /workspace/gemma-test
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import paramiko

HOST = "ssh.runpod.io"
USER = "l8lnmi6ofx0tpz-64411278"
KEY = os.path.expanduser("~/.ssh/id_ed25519")
REMOTE_ROOT = "/workspace/gemma-test"


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: push_to_runpod.py <rel/path> [rel/path ...]")
        return 2
    repo = Path(__file__).resolve().parent.parent
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username=USER, key_filename=KEY, look_for_keys=False, allow_agent=False)
    sftp = c.open_sftp()
    try:
        for arg in sys.argv[1:]:
            src = (repo / arg).resolve()
            if not src.is_file():
                print(f"missing: {src}")
                return 1
            rel = arg.replace("\\", "/").lstrip("/")
            dest = f"{REMOTE_ROOT}/{rel}"
            sftp.put(str(src), dest)
            print(f"put {rel} -> {dest}")
    finally:
        sftp.close()
        c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
