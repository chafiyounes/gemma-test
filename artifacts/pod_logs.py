"""Check FastAPI and inference server logs for error."""
import sys, time, paramiko, re
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("ssh.runpod.io", username="xkebko0395sada-6441173b",
          key_filename=r"C:\Users\pc gamer\.ssh\id_ed25519", timeout=60)
sh = c.invoke_shell(term="xterm-256color", width=220, height=50)
time.sleep(2); sh.recv(65535)
PROMPT = re.compile(r"[#\$] $")

def run(label, cmd, timeout=60):
    print(f"\n>>> {label}")
    sh.send(cmd + "\n")
    buf = ""; t0 = time.time()
    while time.time()-t0 < timeout:
        if sh.recv_ready():
            chunk = sh.recv(65535).decode("utf-8","replace")
            buf += chunk; sys.stdout.write(chunk); sys.stdout.flush()
            if PROMPT.search(buf[-300:]): return buf
        else: time.sleep(0.3)
    print("[TIMEOUT]"); return buf

run("FastAPI errors", "grep -i 'error\\|traceback\\|exception\\|500' /workspace/gemma-test/logs/fastapi.log 2>&1 | tail -30", 30)
run("Inference server tail", "tail -20 /workspace/gemma-test/logs/vllm_gemma4.log 2>&1", 30)
# Direct test of inference server
run("Direct inference test",
    "curl -s -X POST http://localhost:8002/v1/chat/completions "
    "-H 'Content-Type: application/json' "
    "-d '{\"messages\":[{\"role\":\"user\",\"content\":\"Say hello\"}],\"max_tokens\":20}' "
    "2>&1 | python3 -m json.tool 2>&1", 120)
print("DONE")
sh.close(); c.close()
