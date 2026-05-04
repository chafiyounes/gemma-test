"""Check disk + clean root FS, redirect installs to /workspace."""
import sys, time, paramiko, re
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("ssh.runpod.io", username="xkebko0395sada-6441173b",
          key_filename=r"C:\Users\pc gamer\.ssh\id_ed25519", timeout=60)
sh = c.invoke_shell(term="xterm-256color", width=200, height=50)
time.sleep(2); sh.recv(65535)
PROMPT = re.compile(r"[#\$] $")

def run(cmd, timeout=600):
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

run("df -h / /workspace 2>&1", 30)
run("du -sh /root/.cache 2>/dev/null; du -sh /tmp 2>/dev/null; du -sh /usr/local/lib/python3.11/dist-packages 2>/dev/null", 60)
# Clean caches
run("rm -rf /root/.cache/pip /root/.cache/huggingface/xet /tmp/* 2>/dev/null; pip cache purge 2>&1 | tail -2", 120)
run("df -h / 2>&1", 30)
print("DONE")
sh.close(); c.close()
