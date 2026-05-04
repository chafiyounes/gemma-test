"""Fetch full vLLM log from pod."""
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

s.send("cat /workspace/gemma-test/logs/vllm_gemma4.log | head -200\n"); wait(s, 30)
print("\n\n=== TAIL ===\n")
s.send("cat /workspace/gemma-test/logs/vllm_gemma4.log | tail -100\n"); wait(s, 30)
print("\n\n=== GREP ROOT CAUSE ===\n")
s.send("grep -nE 'Error|Exception|Traceback|root cause|raise |OOM|out of memory|cuda' /workspace/gemma-test/logs/vllm_gemma4.log | head -50\n"); wait(s, 30)

s.close(); c.close()
