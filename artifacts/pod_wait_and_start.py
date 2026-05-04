"""Poll until serve_gemma4 is ready, then start FastAPI and test."""
import sys, time, paramiko, re
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("ssh.runpod.io", username="xkebko0395sada-6441173b",
          key_filename=r"C:\Users\pc gamer\.ssh\id_ed25519", timeout=60)
sh = c.invoke_shell(term="xterm-256color", width=220, height=50)
time.sleep(2); sh.recv(65535)
PROMPT = re.compile(r"[#\$] $")

def run(label, cmd, timeout=120):
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

# Check current server state
run("Check serve_gemma4 running", "pgrep -a -f serve_gemma4 2>&1 || echo NOT_RUNNING", 30)
run("Show log tail", "tail -5 /workspace/gemma-test/logs/vllm_gemma4.log 2>&1", 30)
run("Check port 8002", "curl -sf http://localhost:8002/health 2>&1 || echo NOT_READY", 30)

# If server died, restart it
run("Ensure server running", 
    "if ! pgrep -f serve_gemma4 > /dev/null; then "
    "  echo RESTARTING; "
    "  MODEL_DIR=/workspace/models/gemma4-26b-it PORT=8002 "
    "  nohup python3 /workspace/gemma-test/scripts/serve_gemma4.py "
    "  >> /workspace/gemma-test/logs/vllm_gemma4.log 2>&1 & echo NEW_PID=$!; "
    "else echo ALREADY_RUNNING_PID=$(pgrep -f serve_gemma4); fi", 30)

# Poll until ready — up to 40 min total
print("\n>>> Polling until server ready (up to 40 min)...")
sh.send("for i in $(seq 1 240); do sleep 10; "
        "if curl -sf http://localhost:8002/health > /dev/null 2>&1; then echo SERVER_READY_AT=${i}; break; fi; "
        "if ! pgrep -f serve_gemma4 > /dev/null; then echo SERVER_DIED; "
        "  tail -20 /workspace/gemma-test/logs/vllm_gemma4.log; break; fi; "
        # Every 6th iteration (1 min) show progress
        "if (( i % 6 == 0 )); then echo \"[${i}/240] $(tail -2 /workspace/gemma-test/logs/vllm_gemma4.log 2>/dev/null | tr '\\n' '|' | head -c 200)\"; fi; "
        "done\n")
buf = ""; t0 = time.time()
while time.time() - t0 < 2450:  # 40 min
    if sh.recv_ready():
        chunk = sh.recv(65535).decode("utf-8", errors="replace")
        buf += chunk; sys.stdout.write(chunk); sys.stdout.flush()
        if "SERVER_READY" in buf or "SERVER_DIED" in buf:
            break
    else:
        time.sleep(1)

if "SERVER_READY" not in buf:
    print("\n[ERROR] Server not ready after 40 min or died")
    run("Full log tail", "tail -40 /workspace/gemma-test/logs/vllm_gemma4.log 2>&1", 30)
    sh.close(); c.close(); sys.exit(1)

print("\n[INFO] Server ready! Starting FastAPI...")

# Start FastAPI
run("Kill old uvicorn", "pkill -f 'uvicorn api.main' 2>/dev/null; sleep 2; echo done", 30)
run("Start FastAPI",
    "cd /workspace/gemma-test && "
    "nohup python3 -m uvicorn api.main:app --host 0.0.0.0 --port 8000 "
    "> /workspace/gemma-test/logs/fastapi.log 2>&1 & "
    "echo FASTAPI_PID=$! && sleep 8 && "
    "curl -sf http://localhost:8000/health && echo FASTAPI_OK || "
    "(echo FASTAPI_FAIL; tail -20 /workspace/gemma-test/logs/fastapi.log)", 60)

# End-to-end chat test
run("Chat test",
    "curl -s -X POST http://localhost:8000/chat "
    "-H 'Content-Type: application/json' "
    "-d '{\"message\":\"Comment gerer un colis endommage ?\",\"session_id\":\"test1\",\"category\":\"Gestion\"}' "
    "2>&1 | python3 -c 'import json,sys; d=json.load(sys.stdin); print(\"RESPONSE:\", d.get(\"response\",d)[:500])' 2>&1",
    180)

print("\n=== DEPLOY COMPLETE ===")
sh.close(); c.close()
