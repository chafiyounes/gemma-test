"""Smart deploy: diagnose vLLM crash, install python-docx, verify end-to-end."""
import paramiko
import time
import re

KEY_PATH = r"C:/Users/pc gamer/.ssh/id_ed25519"
HOST = "ssh.runpod.io"
USER = "xkebko0395sada-6441173b"
PROMPT_RE = re.compile(r"[#$]\s*$")


def wait_for_prompt(shell, timeout=600):
    buf = ""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if shell.recv_ready():
            chunk = shell.recv(8192).decode("utf-8", errors="replace")
            buf += chunk
            print(chunk, end="", flush=True)
        else:
            last = buf.rstrip()
            if last and PROMPT_RE.search(last[-5:]):
                break
            time.sleep(0.2)
    return buf


def run(shell, label, cmd, timeout=600):
    print(f"\n{'='*70}\n>>> {label}\n{'='*70}", flush=True)
    shell.send(cmd + "\n")
    return wait_for_prompt(shell, timeout)


def main():
    print("Connecting to RunPod...")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=HOST, username=USER, key_filename=KEY_PATH,
        timeout=30, look_for_keys=False, allow_agent=False,
    )
    shell = client.invoke_shell(term="xterm-256color", width=220, height=50)
    shell.settimeout(600)
    time.sleep(2)
    wait_for_prompt(shell, timeout=15)

    STEPS = [
        ("Show last vLLM crash log",
         "echo '=== CRASH LOG (tail 80) ===' && tail -80 /workspace/gemma-test/logs/vllm_gemmaroc.log 2>/dev/null || echo 'no log file'",
         15),
        ("vLLM version + GPU",
         "python3 -c 'import vllm; print(\"vLLM:\", vllm.__version__)' 2>&1; "
         "nvidia-smi --query-gpu=name,memory.total,memory.free --format=csv",
         20),
        ("Pull latest code",
         "cd /workspace/gemma-test && git fetch origin && git reset --hard origin/main && echo RESET_OK",
         30),
        ("Fix line endings + chmod",
         "sed -i 's/\\r//' /workspace/gemma-test/scripts/*.sh /workspace/gemma-test/start_all.sh 2>/dev/null && "
         "chmod +x /workspace/gemma-test/scripts/*.sh /workspace/gemma-test/start_all.sh && echo OK",
         10),
        ("Install python-docx",
         "pip install python-docx==1.1.2 2>&1 | tail -3",
         60),
        ("Verify doc loader works locally",
         "cd /workspace/gemma-test && ls data/documents/*.docx 2>/dev/null | wc -l && "
         "python3 -c 'from core.documents import get_store; s=get_store(); print(f\"Loaded {len(s.docs)} docs\")' 2>&1 | tail -5",
         30),
        ("Kill stale vLLM/uvicorn + free ports",
         "pkill -9 -f 'vllm' 2>/dev/null; pkill -9 -f 'uvicorn' 2>/dev/null; "
         "fuser -k 8001/tcp 2>/dev/null; fuser -k 8000/tcp 2>/dev/null; sleep 3 && echo CLEAN",
         15),
        ("Set VLLM_MODEL_NAME=gemmaroc",
         "sed -i 's/^VLLM_MODEL_NAME=.*/VLLM_MODEL_NAME=gemmaroc/' /workspace/gemma-test/.env && "
         "grep VLLM_MODEL_NAME /workspace/gemma-test/.env",
         5),
        ("Start vLLM (gemmaroc, 2x A40, 16K ctx)",
         "mkdir -p /workspace/gemma-test/logs && rm -f /workspace/gemma-test/logs/vllm_gemmaroc.log && "
         "cd /workspace/gemma-test && "
         "nohup bash scripts/start_vllm.sh gemmaroc > logs/vllm_gemmaroc.log 2>&1 & "
         "echo VLLM_PID=$! && sleep 10 && "
         "echo '--- log first 50 lines ---' && head -50 logs/vllm_gemmaroc.log",
         40),
        ("Poll vLLM /health (up to 8 min)",
         "for i in $(seq 1 48); do "
         "  sleep 10; "
         "  if curl -sf http://localhost:8001/health > /dev/null 2>&1; then "
         "    echo VLLM_READY_${i}; break; "
         "  fi; "
         "  if ! pgrep -f 'vllm' > /dev/null; then "
         "    echo VLLM_DIED; tail -30 /workspace/gemma-test/logs/vllm_gemmaroc.log; break; "
         "  fi; "
         "  echo \"[$i/48] $(tail -1 /workspace/gemma-test/logs/vllm_gemmaroc.log 2>/dev/null | head -c 180)\"; "
         "done",
         520),
        ("vLLM final status",
         "if curl -sf http://localhost:8001/health > /dev/null 2>&1; then echo VLLM_OK; "
         "curl -s http://localhost:8001/v1/models | python3 -m json.tool; "
         "else echo VLLM_FAILED; tail -60 /workspace/gemma-test/logs/vllm_gemmaroc.log; fi",
         15),
        ("Start FastAPI backend",
         "cd /workspace/gemma-test && rm -f logs/api.log && "
         "nohup bash scripts/start_api.sh > logs/api.log 2>&1 & "
         "echo API_PID=$! && sleep 10 && tail -30 logs/api.log",
         25),
        ("Test API /health",
         "curl -s http://localhost:8000/health | python3 -m json.tool 2>&1 || echo 'no response'",
         15),
        ("Test API /models",
         "curl -s http://localhost:8000/models | python3 -m json.tool 2>&1",
         10),
        ("Login + chat smoke test",
         "rm -f /tmp/cj.txt && "
         "curl -s -c /tmp/cj.txt -X POST http://localhost:8000/auth/login "
         "-H 'Content-Type: application/json' "
         "-d '{\"password\":\"user1234\"}' | python3 -m json.tool 2>&1 | head -10; "
         "echo '--- chat ---'; "
         "curl -s -b /tmp/cj.txt -X POST http://localhost:8000/chat "
         "-H 'Content-Type: application/json' "
         "-d '{\"message\":\"Comment gerer un colis perdu en livraison?\",\"session_id\":\"test1\"}' "
         "| python3 -m json.tool 2>&1 | head -40",
         180),
        ("Final summary",
         "echo '=== HEALTH ===' && curl -s http://localhost:8000/health | python3 -m json.tool; "
         "echo '=== vLLM tail ===' && tail -5 /workspace/gemma-test/logs/vllm_gemmaroc.log; "
         "echo '=== API tail ===' && tail -5 /workspace/gemma-test/logs/api.log",
         10),
    ]

    for label, cmd, timeout in STEPS:
        run(shell, label, cmd, timeout)

    shell.close()
    client.close()
    print("\n\n=== DEPLOYMENT COMPLETE ===")
    print("Open http://localhost:8000 — password: user1234")
    print("Admin: http://localhost:8000/admin — password: admin1234")


if __name__ == "__main__":
    main()
