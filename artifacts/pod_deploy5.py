"""Deploy with transformers inference server."""
import sys, time, paramiko, re
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HOST = "ssh.runpod.io"
USER = "xkebko0395sada-6441173b"
KEY  = r"C:\Users\pc gamer\.ssh\id_ed25519"

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, key_filename=KEY, timeout=60)
sh = c.invoke_shell(term="xterm-256color", width=220, height=50)
time.sleep(2); sh.recv(65535)
PROMPT = re.compile(r"[#\$] $")

def run(label, cmd, timeout=300):
    sep = "=" * 70
    print(f"\n{sep}\n>>> {label}\n{sep}")
    sh.send(cmd + "\n")
    buf = ""; t0 = time.time()
    while time.time() - t0 < timeout:
        if sh.recv_ready():
            chunk = sh.recv(65535).decode("utf-8", errors="replace")
            buf += chunk; sys.stdout.write(chunk); sys.stdout.flush()
            if PROMPT.search(buf[-300:]): return buf
        else:
            time.sleep(0.3)
    print("\n[TIMEOUT]"); return buf

# 1. Clean disk
run("Disk free", "df -h / /workspace 2>&1", 30)
run("Clean root cache", "rm -rf /root/.cache/pip /tmp/pip-* 2>/dev/null; pip cache purge 2>&1 | tail -2; df -h / 2>&1", 60)

# 2. Install only what's needed (small packages)
run("Install uvicorn + accelerate", 
    "pip install --no-cache-dir uvicorn[standard] accelerate 2>&1 | tail -10", 180)

# 3. Pull latest code
run("Git pull", 
    "cd /workspace/gemma-test && git fetch origin main && git reset --hard FETCH_HEAD && echo RESET_OK && git log -1 --oneline", 60)

# 4. Fix line endings + chmod
run("Fix scripts", 
    "sed -i 's/\\r//' /workspace/gemma-test/scripts/*.sh /workspace/gemma-test/scripts/*.py /workspace/gemma-test/start_all.sh 2>/dev/null; chmod +x /workspace/gemma-test/scripts/*.sh /workspace/gemma-test/start_all.sh; echo OK", 30)

# 5. Kill old processes
run("Kill old processes", 
    "pkill -9 -f 'serve_gemma4|vllm|uvicorn' 2>/dev/null; sleep 3; ss -tlnp 2>/dev/null | grep -E ':(8000|8002)' || echo 'ports free'", 30)

# 6. Verify model + CUDA
run("Verify model + CUDA",
    "ls /workspace/models/gemma4-26b-it/config.json && python3 -c 'import torch; print(\"CUDA:\", torch.cuda.is_available(), \"GPUs:\", torch.cuda.device_count())' 2>&1", 30)

# 7. Start inference server in background
run("Start inference server",
    "mkdir -p /workspace/gemma-test/logs && "
    "MODEL_DIR=/workspace/models/gemma4-26b-it PORT=8002 "
    "nohup python3 /workspace/gemma-test/scripts/serve_gemma4.py "
    "> /workspace/gemma-test/logs/vllm_gemma4.log 2>&1 & echo SERVER_PID=$!", 30)

# 8. Wait for server to load model (up to 10 min — 52GB model takes a while)
print("\n>>> Waiting for inference server to load model (up to 10 min)...")
sh.send("for i in $(seq 1 60); do sleep 10; "
        "if curl -sf http://localhost:8002/health > /dev/null 2>&1; then echo SERVER_READY_${i}; break; fi; "
        "if ! pgrep -f serve_gemma4 > /dev/null; then echo SERVER_DIED; "
        "  tail -30 /workspace/gemma-test/logs/vllm_gemma4.log; break; fi; "
        "echo \"[$i/60] $(tail -1 /workspace/gemma-test/logs/vllm_gemma4.log 2>/dev/null | head -c 160)\"; done\n")
buf = ""; t0 = time.time()
while time.time() - t0 < 650:
    if sh.recv_ready():
        chunk = sh.recv(65535).decode("utf-8", errors="replace")
        buf += chunk; sys.stdout.write(chunk); sys.stdout.flush()
        if "SERVER_READY" in buf or "SERVER_DIED" in buf:
            break
    else:
        time.sleep(1)

if "SERVER_READY" not in buf:
    print("\n[ERROR] Server not ready — check logs above")
    sh.close(); c.close(); sys.exit(1)

# 9. Start FastAPI
run("Set env + start FastAPI",
    "cd /workspace/gemma-test && "
    "sed -i 's/^VLLM_MODEL_NAME=.*/VLLM_MODEL_NAME=gemma4/' .env && "
    "sed -i 's|^VLLM_BASE_URL=.*|VLLM_BASE_URL=http://localhost:8002|' .env && "
    "nohup python3 -m uvicorn api.main:app --host 0.0.0.0 --port 8000 "
    "> /workspace/gemma-test/logs/fastapi.log 2>&1 & "
    "echo FASTAPI_PID=$! && sleep 6 && "
    "curl -sf http://localhost:8000/health && echo FASTAPI_OK", 60)

# 10. Test chat endpoint
run("Test chat",
    "curl -s -X POST http://localhost:8000/chat "
    "-H 'Content-Type: application/json' "
    "-d '{\"message\":\"Comment gerer un colis endommage ?\",\"session_id\":\"test1\",\"category\":\"Gestion\"}' "
    "2>&1 | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get(\"response\",d)[:400])' 2>&1 || "
    "echo RAW_RESP: $(curl -s -X POST http://localhost:8000/chat -H 'Content-Type: application/json' -d '{\"message\":\"test\",\"session_id\":\"t1\"}' 2>&1 | head -c 400)",
    120)

print("\n\n=== DEPLOY COMPLETE ===")
sh.close(); c.close()
