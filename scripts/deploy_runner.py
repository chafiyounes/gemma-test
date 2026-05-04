#!/usr/bin/env python3
"""
One-click deployment to RunPod pod.

Usage:
    python scripts/deploy_runner.py              # full deploy
    python scripts/deploy_runner.py --skip-deps  # skip system/Python deps (faster redeploy)

Connects via paramiko (PTY-aware) to bypass RunPod's SSH gateway restriction.
"""
import argparse
import paramiko
import time
import os
import sys
import re

HOST = "ssh.runpod.io"
USER = "l8lnmi6ofx0tpz-64411278"
KEY_PATH = os.path.expanduser("~/.ssh/id_ed25519")

ANSI_RE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')


def safe_print(text):
    """Print text safely on Windows (strip non-ASCII)."""
    clean = ANSI_RE.sub("", text)
    sys.stdout.write(clean.encode("ascii", "replace").decode())
    sys.stdout.flush()


def run_commands(cmds, label="deploy"):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"[{time.strftime('%H:%M:%S')}] Connecting to {USER}@{HOST}...")
    client.connect(HOST, username=USER, key_filename=KEY_PATH,
                   look_for_keys=False, allow_agent=False)

    shell = client.invoke_shell(term="xterm", width=200, height=50)
    shell.settimeout(0.5)
    time.sleep(3)
    while shell.recv_ready():
        shell.recv(8192)

    for i, cmd in enumerate(cmds, 1):
        print(f"\n[{time.strftime('%H:%M:%S')}] ({i}/{len(cmds)}) >>> {cmd}")
        shell.send(cmd + "\r")

        timeout = 1200  # 20 min max per command
        end_time = time.time() + timeout
        full_out = ""

        while time.time() < end_time:
            try:
                if shell.recv_ready():
                    chunk = shell.recv(8192).decode("utf-8", "replace")
                    full_out += chunk
                    safe_print(chunk)

                    clean = ANSI_RE.sub("", full_out)
                    lines = clean.splitlines()
                    if lines:
                        last = lines[-1].strip()
                        if (last.endswith("#") or last.endswith("$")) and cmd[:10] not in last:
                            break
                else:
                    time.sleep(0.5)
            except Exception as e:
                print(f"\n[WARN] Read error: {e}")
                break

    shell.close()
    client.close()
    print(f"\n[{time.strftime('%H:%M:%S')}] DONE: {label} finished.")


def main():
    parser = argparse.ArgumentParser(description="Deploy gemma-test to RunPod")
    parser.add_argument("--skip-deps", action="store_true",
                        help="Skip system and Python dependency installation")
    args = parser.parse_args()

    dep_cmds = []
    if not args.skip_deps:
        dep_cmds = [
            "export DEBIAN_FRONTEND=noninteractive",
            "dpkg --configure -a",
            "apt-get update",
            "apt-get install -y tmux",
            # Node.js 20
            "apt-get install -y ca-certificates curl gnupg",
            "mkdir -p /etc/apt/keyrings",
            "curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg --batch --yes",
            'echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" | tee /etc/apt/sources.list.d/nodesource.list',
            "apt-get update",
            "apt-get install nodejs -y",
            # Python deps
            "python3 -m pip install --upgrade pip",
            "cd /workspace/gemma-test",
            "python3 -m pip install -r requirements.txt",
            "python3 -m pip install bitsandbytes accelerate",
        ]

    deploy_cmds = [
        "cd /workspace/gemma-test",
        "git fetch origin main",
        "git reset --hard FETCH_HEAD",
        # Fix Windows line endings
        "sed -i 's/\\r//' scripts/*.sh start_all.sh",
        "chmod +x scripts/*.sh start_all.sh",
        # Build frontend
        "cd web_test",
        "npm install",
        "npm run build",
        "cd ..",
        # Start services
        "bash start_all.sh gemma4",
    ]

    all_cmds = dep_cmds + deploy_cmds
    run_commands(all_cmds, label="full deploy" if not args.skip_deps else "quick deploy")


if __name__ == "__main__":
    main()
