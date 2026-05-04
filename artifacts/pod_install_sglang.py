"""Install SGLang and test Gemma 4 support."""
import sys, time, paramiko, re
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("ssh.runpod.io", username="xkebko0395sada-6441173b",
          key_filename=r"C:\Users\pc gamer\.ssh\id_ed25519", timeout=60)
sh = c.invoke_shell(term="xterm-256color", width=200, height=50)
time.sleep(2); sh.recv(65535)
PROMPT = re.compile(r"[#\$] $")

def run(cmd, timeout=900):
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

# Install sglang. Pin to compatible version with torch 2.8 cu128.
run("pip install --no-cache-dir 'sglang[all]' --extra-index-url https://download.pytorch.org/whl/cu128 2>&1 | tail -20", 1800)
run("python3 -c 'import sglang; print(\"sglang:\", sglang.__version__)' 2>&1", 60)
# Check if sglang's serving supports Gemma 4 (via transformers fallback)
run("python3 -c 'from sglang.srt.models import registry; print([m for m in registry.ModelRegistry.models.keys() if \"emma\" in m.lower()])' 2>&1 || python3 -c 'import sglang.srt.models; import os; p=os.path.dirname(sglang.srt.models.__file__); import glob; print([os.path.basename(f) for f in glob.glob(p+\"/*.py\") if \"emma\" in f.lower()])' 2>&1", 60)
run("python3 -c 'import torch; print(torch.__version__, torch.cuda.is_available())' 2>&1", 60)
print("DONE")
sh.close(); c.close()
