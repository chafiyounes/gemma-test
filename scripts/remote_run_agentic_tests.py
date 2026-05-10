"""SSH to RunPod (PTY) and run agentic RAG tests. Requires ~/.ssh/id_ed25519."""

from __future__ import annotations

import base64
import os
import re
import sys
import time

import paramiko

HOST = "ssh.runpod.io"
USER = "l8lnmi6ofx0tpz-64411278"
KEY = os.path.expanduser(r"~/.ssh/id_ed25519")
ANSI = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

REMOTE = r"""
set -e
cd /workspace/gemma-test
git fetch origin main
git reset --hard FETCH_HEAD
echo "HEAD $(git rev-parse --short HEAD)"
python3 scripts/bootstrap_agentic_map.py || echo "[warn] bootstrap exit non-zero"
if grep -q '^AGENTIC_RAG_ENABLED=' .env 2>/dev/null; then
  sed -i 's/^AGENTIC_RAG_ENABLED=.*/AGENTIC_RAG_ENABLED=true/' .env
else
  echo 'AGENTIC_RAG_ENABLED=true' >> .env
fi
export ADMIN_PASSWORD=$(grep -E '^ADMIN_SITE_PASSWORD=' .env | head -1 | cut -d= -f2- | tr -d '\r' | tr -d '"' | tr -d "'")
export USER_PASSWORD=$(grep -E '^USER_SITE_PASSWORD=' .env | head -1 | cut -d= -f2- | tr -d '\r' | tr -d '"' | tr -d "'")
bash scripts/restart_api.sh || echo "[warn] API restart failed"
echo "[hint] vLLM tool calling needs a vLLM restart after git pull: bash start_all.sh gemma4 (or restart only the vLLM tmux pane)."
sleep 10
set +e
python3 scripts/test_agentic_rag_pod.py
ec=$?
echo "REMOTE_SCRIPT_DONE exit=$ec"
exit "$ec"
""".strip()


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
    time.sleep(2.0)
    while shell.recv_ready():
        shell.recv(65536)

    b64 = base64.b64encode(REMOTE.encode()).decode("ascii")
    shell.send(f"echo {b64} | base64 -d | bash\n")

    deadline = time.time() + 3600.0
    buf = ""
    while time.time() < deadline:
        try:
            if shell.recv_ready():
                chunk = shell.recv(65536).decode("utf-8", "replace")
                buf += chunk
                clean = ANSI.sub("", chunk)
                sys.stdout.write(clean)
                sys.stdout.flush()
                if "REMOTE_SCRIPT_DONE" in buf:
                    break
            else:
                time.sleep(0.4)
        except (EOFError, TimeoutError):
            time.sleep(0.4)

    shell.close()
    client.close()

    plain = ANSI.sub("", buf)
    m = re.search(r"REMOTE_SCRIPT_DONE exit=(\d+)", plain)
    if m:
        return int(m.group(1))
    if "Done. failures=0" in plain:
        return 0
    print("REMOTE_RUN_INCOMPLETE (no REMOTE_SCRIPT_DONE marker)", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
