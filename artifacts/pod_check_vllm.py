"""Verify vllm 0.11 + check Gemma 4 support, also try starting it."""
import sys, time, paramiko, re
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("ssh.runpod.io", username="xkebko0395sada-6441173b",
          key_filename=r"C:\Users\pc gamer\.ssh\id_ed25519", timeout=60)
sh = c.invoke_shell(term="xterm-256color", width=200, height=50)
time.sleep(2); sh.recv(65535)
PROMPT = re.compile(r"[#\$] $")

def run(cmd, timeout=300):
    print(f"\n>>> {cmd[:200]}")
    sh.send(cmd + "\n")
    buf = ""; t0 = time.time()
    while time.time() - t0 < timeout:
        if sh.recv_ready():
            chunk = sh.recv(65535).decode("utf-8", errors="replace")
            buf += chunk; sys.stdout.write(chunk); sys.stdout.flush()
            if PROMPT.search(buf[-200:]): return buf
        else:
            time.sleep(0.3)
    print("\n[TIMEOUT]"); return buf

run("python3 -c 'import vllm; print(vllm.__version__); import vllm._C; print(\"_C OK\")' 2>&1", 60)
run("pip show transformers 2>&1 | grep -E 'Name|Version'", 30)
run("python3 -c 'from vllm import ModelRegistry; archs = ModelRegistry.get_supported_archs(); print([a for a in archs if \"emma\" in a.lower()])' 2>&1", 60)
run("cat /workspace/models/gemma4-26b-it/config.json | python3 -c 'import json,sys; c=json.load(sys.stdin); print(\"arch:\", c.get(\"architectures\")); print(\"model_type:\", c.get(\"model_type\"))'", 30)
print("DONE")
sh.close(); c.close()
