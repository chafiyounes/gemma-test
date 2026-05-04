"""Reinstall vLLM with cu128 wheels (older version compatible with driver 575)."""
import sys, time, paramiko, re
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HOST = "ssh.runpod.io"
USER = "xkebko0395sada-6441173b"
KEY  = r"C:\Users\pc gamer\.ssh\id_ed25519"

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, key_filename=KEY, timeout=60)
sh = c.invoke_shell(term="xterm-256color", width=200, height=50)
time.sleep(2)
sh.recv(65535)

PROMPT = re.compile(r"[#\$] $")

def run(cmd, timeout=900):
    print(f">>> {cmd[:200]}")
    sh.send(cmd + "\n")
    buf = ""
    t0 = time.time()
    while time.time() - t0 < timeout:
        if sh.recv_ready():
            chunk = sh.recv(65535).decode("utf-8", errors="replace")
            buf += chunk
            sys.stdout.write(chunk)
            sys.stdout.flush()
            if PROMPT.search(buf[-200:]):
                return buf
        else:
            time.sleep(0.3)
    print("\n[TIMEOUT]")
    return buf

# Try vllm 0.11.0 which is the last release with cu128 wheels
run("pip uninstall -y vllm 2>&1 | tail -3", 180)
run("pip install --no-cache-dir 'vllm==0.11.0' --extra-index-url https://download.pytorch.org/whl/cu128 2>&1 | tail -30", 1800)
run("python3 -c 'import vllm; print(\"vllm:\", vllm.__version__); import vllm._C; print(\"_C OK\")' 2>&1", 60)
run("python3 -c 'import torch; print(\"torch:\", torch.__version__, \"cuda:\", torch.cuda.is_available())' 2>&1", 60)
print("DONE")
sh.close(); c.close()
