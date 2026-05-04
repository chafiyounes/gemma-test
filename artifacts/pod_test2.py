"""Test with auth cookie."""
import sys, time, paramiko, re
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("ssh.runpod.io", username="xkebko0395sada-6441173b",
          key_filename=r"C:\Users\pc gamer\.ssh\id_ed25519", timeout=60)
sh = c.invoke_shell(term="xterm-256color", width=220, height=50)
time.sleep(2); sh.recv(65535)
PROMPT = re.compile(r"[#\$] $")

def run(label, cmd, timeout=240):
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

# Check password from .env on pod
run("Check .env passwords", "grep -E 'PASSWORD|SECRET' /workspace/gemma-test/.env 2>&1 | grep -v HF_TOKEN", 30)

# Login and get cookie
run("Login + chat test",
    "curl -sc /tmp/cookies.txt -s -X POST http://localhost:8000/auth/login "
    "-H 'Content-Type: application/json' "
    "-d '{\"password\":\"user1234\"}' && echo LOGIN_OK && "
    "curl -s -b /tmp/cookies.txt -X POST http://localhost:8000/chat "
    "-H 'Content-Type: application/json' "
    "-d '{\"message\":\"Comment gerer un colis endommage ?\",\"session_id\":\"test1\",\"category\":\"Gestion\"}' "
    "2>&1 | python3 -m json.tool 2>&1 | cut -c1-3000", 240)

print("\nDONE")
sh.close(); c.close()
