"""Quick diag: check model name + fastapi error log + direct inference test."""
import sys, time, paramiko, re
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("ssh.runpod.io", username="xkebko0395sada-6441173b",
          key_filename=r"C:\Users\pc gamer\.ssh\id_ed25519", timeout=60)
sh = c.invoke_shell(term="xterm-256color", width=220, height=50)
time.sleep(2); sh.recv(65535)
PROMPT = re.compile(r"[#\$] $")

def run(label, cmd, t=120):
    print(f"\n>>> {label}")
    sh.send(cmd + "\n")
    buf=""; t0=time.time()
    while time.time()-t0 < t:
        if sh.recv_ready():
            chunk=sh.recv(65535).decode("utf-8","replace")
            buf+=chunk; sys.stdout.write(chunk); sys.stdout.flush()
            if PROMPT.search(buf[-200:]): return buf
        else: time.sleep(0.3)
    print("[T/O]"); return buf

run("model list", "curl -s http://localhost:8002/v1/models", 30)
run("fastapi error log", "grep -i 'error\\|500\\|exception\\|traceback' /workspace/gemma-test/logs/fastapi.log | tail -20", 30)
run("direct inference",
    "curl -s -X POST http://localhost:8002/v1/chat/completions "
    "-H 'Content-Type: application/json' "
    "-d '{\"messages\":[{\"role\":\"user\",\"content\":\"Reply with just: hi\"}],\"max_tokens\":10}' "
    "| python3 -m json.tool", 120)
print("\nDONE"); sh.close(); c.close()
