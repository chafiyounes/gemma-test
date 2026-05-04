"""Quick pod status probe."""
import os, time, re, sys
from pathlib import Path
import paramiko

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HOST = "ssh.runpod.io"; USER = "xkebko0395sada-6441173b"
KEY_PATH = str(Path.home() / ".ssh" / "id_ed25519")
PROMPT_RE = re.compile(r"[#$]\s*$")

def wait_for_prompt(shell, timeout=30):
    buf = ""; deadline = time.time() + timeout
    while time.time() < deadline:
        if shell.recv_ready():
            chunk = shell.recv(65536).decode("utf-8", errors="replace")
            buf += chunk; sys.stdout.write(chunk); sys.stdout.flush()
            tail = buf.splitlines()[-1] if buf.splitlines() else ""
            if PROMPT_RE.search(tail[-5:]): return buf
        else: time.sleep(0.1)
    return buf

c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, key_filename=KEY_PATH, timeout=30,
          look_for_keys=False, allow_agent=False)
s = c.invoke_shell(term="xterm-256color", width=220, height=50); s.settimeout(60)
time.sleep(2); wait_for_prompt(s, 15)

cmds = [
    "ps aux | grep -E 'snapshot_download|dl_gemma4|hf_hub' | grep -v grep",
    "ls -la /workspace/models/gemma4-26b-it/ 2>/dev/null",
    "du -sh /workspace/models/gemma4-26b-it 2>/dev/null",
    "test -f /workspace/models/gemma4-26b-it/config.json && echo CONFIG_OK || echo NO_CONFIG",
    "find /workspace/models/gemma4-26b-it -name '*.incomplete' 2>/dev/null | head -5",
    "find /workspace/models/gemma4-26b-it -name '*.safetensors' 2>/dev/null | xargs -I{} ls -la {} 2>/dev/null",
    "cat /tmp/gemma4_dl.log 2>/dev/null | tail -10",
]
for cmd in cmds:
    print(f"\n>>> {cmd}")
    s.send(cmd + "\n"); wait_for_prompt(s, 30)

s.close(); c.close()
