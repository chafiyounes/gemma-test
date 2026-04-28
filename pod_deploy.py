"""Smart deploy v3:
1. SFTP all .docx documents to pod
2. Reliable git reset (FETCH_HEAD)
3. vLLM on port 8002 (avoid stale sidecar on 8001)
4. Update .env to point at port 8002
5. End-to-end chat test
"""
import paramiko
import time
import re
import sys
from pathlib import Path

KEY_PATH = r"C:/Users/pc gamer/.ssh/id_ed25519"
HOST = "ssh.runpod.io"
USER = "xkebko0395sada-6441173b"
PROMPT_RE = re.compile(r"[#$]\s*$")
LOCAL_DOCS = Path(r"C:/Users/pc gamer/OneDrive/Desktop/full project/gemma-test/data/documents")
REMOTE_DOCS = "/workspace/gemma-test/data/documents"


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


def upload_docs(client):
    print("\n" + "="*70)
    print(">>> SFTP: Uploading 60 documents to /workspace/gemma-test/data/documents/")
    print("="*70)
    sftp = client.open_sftp()
    # Ensure remote dir exists
    try:
        sftp.stat(REMOTE_DOCS)
    except FileNotFoundError:
        # mkdir -p equivalent via shell would be safer, but try one level
        try:
            sftp.mkdir(REMOTE_DOCS)
        except Exception:
            pass
    files = sorted(LOCAL_DOCS.glob("*.docx"))
    print(f"Found {len(files)} local .docx files")
    uploaded = 0
    for f in files:
        remote_path = f"{REMOTE_DOCS}/{f.name}"
        try:
            sftp.put(str(f), remote_path)
            uploaded += 1
            if uploaded % 10 == 0:
                print(f"  Uploaded {uploaded}/{len(files)}...")
        except Exception as exc:
            print(f"  FAIL {f.name}: {exc}")
    sftp.close()
    print(f"✓ Uploaded {uploaded}/{len(files)} files")


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

    # ── First: ensure target dir exists, then SFTP ──
    run(shell, "Ensure docs dir exists",
        "mkdir -p /workspace/gemma-test/data/documents && rm -f /workspace/gemma-test/data/documents/*.docx 2>/dev/null; ls -la /workspace/gemma-test/data/documents/ | head -3",
        15)
    upload_docs(client)

    STEPS = [
        ("Verify uploaded docs",
         "ls /workspace/gemma-test/data/documents/*.docx | wc -l && du -sh /workspace/gemma-test/data/documents/",
         15),
        ("Pull latest code (FETCH_HEAD)",
         "cd /workspace/gemma-test && git fetch origin main && git reset --hard FETCH_HEAD && echo RESET_OK && git log -1 --oneline",
         30),
        ("Fix line endings + chmod",
         "sed -i 's/\\r//' /workspace/gemma-test/scripts/*.sh /workspace/gemma-test/start_all.sh 2>/dev/null && "
         "chmod +x /workspace/gemma-test/scripts/*.sh /workspace/gemma-test/start_all.sh && echo OK",
         10),
        ("Install python-docx",
         "pip install python-docx==1.1.2 2>&1 | tail -3",
         60),
        ("Test doc loader (should load 60 docs)",
         "cd /workspace/gemma-test && "
         "python3 -c 'from core.documents import get_store; s=get_store(); "
         "print(f\"Loaded {len(s.docs)} docs, avgdl={int(s.avgdl)} tokens\"); "
         "top = s.retrieve(\"colis perdu en livraison\", k=3); "
         "print(\"Top 3:\", [d.name for d in top])' 2>&1 | tail -10",
         30),
        ("Aggressive process cleanup",
         "pkill -9 -f 'vllm' 2>/dev/null; pkill -9 -f 'uvicorn' 2>/dev/null; "
         "for p in 8000 8001 8002; do fuser -k $p/tcp 2>/dev/null; done; sleep 4; "
         "echo '--- ports after kill ---'; ss -tlnp 2>/dev/null | grep -E ':(8000|8001|8002)' || echo 'all clear'",
         20),
        ("Update .env: VLLM_BASE_URL on port 8002",
         "sed -i 's|^VLLM_BASE_URL=.*|VLLM_BASE_URL=http://localhost:8002|' /workspace/gemma-test/.env && "
         "sed -i 's/^VLLM_MODEL_NAME=.*/VLLM_MODEL_NAME=gemmaroc/' /workspace/gemma-test/.env && "
         "grep -E 'VLLM_(BASE_URL|MODEL_NAME)' /workspace/gemma-test/.env",
         5),
        ("Start vLLM on port 8002",
         "mkdir -p /workspace/gemma-test/logs && rm -f /workspace/gemma-test/logs/vllm_gemmaroc.log && "
         "cd /workspace/gemma-test && "
         "nohup bash scripts/start_vllm.sh gemmaroc > logs/vllm_gemmaroc.log 2>&1 & "
         "echo VLLM_PID=$! && sleep 10 && "
         "echo '--- log first 30 lines ---' && head -30 logs/vllm_gemmaroc.log",
         40),
        ("Wait for vLLM ready on 8002 (up to 8 min)",
         "for i in $(seq 1 48); do "
         "  sleep 10; "
         "  if curl -sf http://localhost:8002/health > /dev/null 2>&1; then "
         "    if curl -sf http://localhost:8002/v1/models > /dev/null 2>&1; then "
         "      echo VLLM_FULLY_READY_${i}; break; "
         "    fi; "
         "  fi; "
         "  if ! pgrep -f 'vllm' > /dev/null; then "
         "    echo VLLM_PROCESS_DIED; tail -40 /workspace/gemma-test/logs/vllm_gemmaroc.log; break; "
         "  fi; "
         "  echo \"[$i/48] $(tail -1 /workspace/gemma-test/logs/vllm_gemmaroc.log 2>/dev/null | head -c 180)\"; "
         "done",
         520),
        ("vLLM /v1/models check",
         "curl -s http://localhost:8002/v1/models | python3 -m json.tool 2>&1 | head -30",
         15),
        ("Start FastAPI",
         "cd /workspace/gemma-test && rm -f logs/api.log && "
         "nohup bash scripts/start_api.sh > logs/api.log 2>&1 & "
         "echo API_PID=$! && sleep 8 && tail -25 logs/api.log",
         25),
        ("Test /health",
         "sleep 3 && curl -s http://localhost:8000/health | python3 -m json.tool",
         15),
        ("Login + chat with SOP question",
         "rm -f /tmp/cj.txt && "
         "curl -s -c /tmp/cj.txt -X POST http://localhost:8000/auth/login "
         "-H 'Content-Type: application/json' -d '{\"password\":\"user1234\"}' "
         "| python3 -m json.tool | head -5; "
         "echo '--- chat test ---'; "
         "curl -s -b /tmp/cj.txt -X POST http://localhost:8000/chat "
         "-H 'Content-Type: application/json' "
         "-d '{\"message\":\"Comment dois-je gerer un colis perdu en livraison?\",\"session_id\":\"test1\"}' "
         "| python3 -m json.tool 2>&1 | head -50",
         300),
        ("Final summary",
         "echo '=== HEALTH ===' && curl -s http://localhost:8000/health | python3 -m json.tool; "
         "echo '=== vLLM tail ===' && tail -8 /workspace/gemma-test/logs/vllm_gemmaroc.log; "
         "echo '=== API tail ===' && tail -8 /workspace/gemma-test/logs/api.log",
         10),
    ]

    for label, cmd, timeout in STEPS:
        run(shell, label, cmd, timeout)

    shell.close()
    client.close()
    print("\n\n=== DEPLOYMENT COMPLETE ===")
    print("Open http://localhost:8000  —  password: user1234")


if __name__ == "__main__":
    main()
