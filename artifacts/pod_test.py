"""Final test + report."""
import sys, time, paramiko, re
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("ssh.runpod.io", username="xkebko0395sada-6441173b",
          key_filename=r"C:\Users\pc gamer\.ssh\id_ed25519", timeout=60)
sh = c.invoke_shell(term="xterm-256color", width=220, height=50)
time.sleep(2); sh.recv(65535)
PROMPT = re.compile(r"[#\$] $")

def run(label, cmd, timeout=180):
    print(f"\n>>> {label}")
    sh.send(cmd + "\n")
    buf = ""; t0 = time.time()
    while time.time() - t0 < timeout:
        if sh.recv_ready():
            chunk = sh.recv(65535).decode("utf-8", errors="replace")
            buf += chunk; sys.stdout.write(chunk); sys.stdout.flush()
            if PROMPT.search(buf[-300:]): return buf
        else: time.sleep(0.3)
    print("\n[TIMEOUT]"); return buf

run("Process check", "pgrep -a -f 'serve_gemma4|uvicorn' 2>&1", 30)
run("Health checks", "curl -sf http://localhost:8002/health && echo ; curl -sf http://localhost:8000/health && echo", 30)
run("Raw chat response (truncated)",
    "curl -s -X POST http://localhost:8000/chat "
    "-H 'Content-Type: application/json' "
    "-d '{\"message\":\"Comment gerer un colis endommage ?\",\"session_id\":\"test1\",\"category\":\"Gestion\"}' "
    "2>&1 | head -c 2000", 180)
print("\nDONE")
sh.close(); c.close()
