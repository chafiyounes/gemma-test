"""Diagnose CUDA / torch / driver versions on pod."""
import os, time, re, sys
from pathlib import Path
import paramiko

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HOST = "ssh.runpod.io"; USER = "xkebko0395sada-6441173b"
KEY_PATH = str(Path.home() / ".ssh" / "id_ed25519")
PROMPT_RE = re.compile(r"[#$]\s*$")

def wait(s, t=120):
    buf = ""; d = time.time() + t
    while time.time() < d:
        if s.recv_ready():
            ch = s.recv(65536).decode("utf-8", "replace")
            buf += ch; sys.stdout.write(ch); sys.stdout.flush()
            tail = buf.splitlines()[-1] if buf.splitlines() else ""
            if PROMPT_RE.search(tail[-5:]): return buf
        else: time.sleep(0.1)
    return buf

c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, key_filename=KEY_PATH, timeout=30,
          look_for_keys=False, allow_agent=False)
s = c.invoke_shell(term="xterm-256color", width=220, height=50); s.settimeout(120)
time.sleep(2); wait(s, 15)

cmds = [
    "nvidia-smi | head -10",
    "nvidia-smi --query-gpu=driver_version --format=csv,noheader",
    "python3 -c 'import torch; print(\"torch:\", torch.__version__); print(\"cuda compiled:\", torch.version.cuda); print(\"cuda available:\", torch.cuda.is_available()); print(\"device count:\", torch.cuda.device_count())' 2>&1",
    "python3 -c 'import torch; print(torch.cuda.get_device_name(0))' 2>&1 || echo CUDA_INIT_FAIL",
    "pip show vllm 2>/dev/null | grep -E 'Name|Version'",
    "pip show torch 2>/dev/null | grep -E 'Name|Version'",
    "pip show transformers 2>/dev/null | grep -E 'Name|Version'",
]
for cmd in cmds:
    print(f"\n>>> {cmd}")
    s.send(cmd + "\n"); wait(s, 30)

s.close(); c.close()
