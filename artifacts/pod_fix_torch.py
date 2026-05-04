"""Reinstall torch+vllm with CUDA 12.8 wheels matching driver 575.57.08."""
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
s = c.invoke_shell(term="xterm-256color", width=220, height=50); s.settimeout(3600)
time.sleep(2); wait(s, 15)

# 1) Kill any vLLM / uvicorn first
s.send("pkill -9 -f 'vllm' 2>/dev/null; pkill -9 -f 'uvicorn' 2>/dev/null; sleep 2; echo killed\n"); wait(s, 30)

# 2) Uninstall torch stack (ignore errors)
s.send("pip uninstall -y torch torchvision torchaudio xformers vllm 2>&1 | tail -10\n"); wait(s, 300)

# 3) Reinstall vllm 0.20.0 forcing cu128 torch
#    vllm 0.20.0 has wheels for cu126/cu128. cu128 is the closest match for driver 12.9.
s.send("pip install --no-cache-dir 'vllm==0.20.0' --extra-index-url https://download.pytorch.org/whl/cu128 2>&1 | tail -30\n"); wait(s, 1800)

# 4) Verify
s.send("python3 -c 'import torch; print(\"torch:\", torch.__version__, \"cuda compiled:\", torch.version.cuda, \"avail:\", torch.cuda.is_available(), \"name:\", torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"NO\")' 2>&1\n"); wait(s, 60)
s.send("pip show vllm 2>/dev/null | grep -E 'Name|Version'\n"); wait(s, 30)

s.close(); c.close()
print("\n=== DRIVER FIX DONE ===")
