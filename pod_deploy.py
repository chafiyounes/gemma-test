"""Smart deploy v4:

Plan:
1. SCP the 10 SOP docs (2 categories) to the pod (uses Windows scp.exe)
2. Pull latest code from GitHub (via FETCH_HEAD)
3. Install python-docx
4. Try to download Gemma 4 26B; fall back to GemMaroc-27b-it if unavailable
5. Start vLLM on port 8002 (avoids stale RunPod sidecar on 8001)
6. Start FastAPI on port 8000
7. Run end-to-end chat test against /categories + /chat
"""
import paramiko
import subprocess
import time
import re
import sys
import os
from pathlib import Path

KEY_PATH = r"C:\Users\pc gamer\.ssh\id_ed25519"
HOST = "ssh.runpod.io"
USER = "xkebko0395sada-6441173b"
SSH_ALIAS = "runpod2"
PROMPT_RE = re.compile(r"[#$]\s*$")

LOCAL_ROOT = Path(r"C:\Users\pc gamer\OneDrive\Desktop\full project\gemma-test")
LOCAL_DOCS = LOCAL_ROOT / "data" / "documents"
REMOTE_PROJECT = "/workspace/gemma-test"
REMOTE_DOCS = f"{REMOTE_PROJECT}/data/documents"

# HF token: read from env var or .env file (kept out of git)
HF_TOKEN = os.environ.get("HF_TOKEN", "")
if not HF_TOKEN:
    env_file = LOCAL_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("HF_TOKEN="):
                HF_TOKEN = line.split("=", 1)[1].strip()
                break
if not HF_TOKEN:
    print("WARNING: HF_TOKEN not set in env or .env — gated model downloads will fail")


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


def scp_upload_docs():
    """Use Windows scp.exe (subprocess) to upload the docs/ tree."""
    print("\n" + "="*70)
    print(">>> SCP: Uploading data/documents/ to pod")
    print("="*70)
    if not LOCAL_DOCS.is_dir():
        print(f"FATAL: {LOCAL_DOCS} not found")
        sys.exit(1)
    # -O = use legacy SCP protocol (more reliable on RunPod gateway)
    # -r = recursive
    cmd = [
        "scp", "-O", "-r",
        "-o", "StrictHostKeyChecking=no",
        str(LOCAL_DOCS),
        f"{SSH_ALIAS}:{REMOTE_PROJECT}/data/",
    ]
    print("Running:", " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    print(proc.stdout)
    if proc.returncode != 0:
        print("scp stderr:", proc.stderr)
        # Fallback: try without -O (newer SCP)
        print("Retrying without -O ...")
        cmd2 = ["scp", "-r", "-o", "StrictHostKeyChecking=no",
                str(LOCAL_DOCS), f"{SSH_ALIAS}:{REMOTE_PROJECT}/data/"]
        proc = subprocess.run(cmd2, capture_output=True, text=True, timeout=600)
        print(proc.stdout)
        if proc.returncode != 0:
            print("scp failed:", proc.stderr)
            sys.exit(1)
    print("✓ SCP done")


def main():
    # ── Step 0: SCP docs first (independent of SSH session) ──
    scp_upload_docs()

    print("\nConnecting to RunPod via SSH...")
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
        ("Verify docs uploaded by SCP",
         f"find {REMOTE_DOCS} -name '*.docx' | wc -l && ls {REMOTE_DOCS}/",
         15),
        ("Pull latest code (FETCH_HEAD)",
         f"cd {REMOTE_PROJECT} && git fetch origin main && git reset --hard FETCH_HEAD && "
         "echo RESET_OK && git log -1 --oneline",
         60),
        ("Fix line endings + chmod",
         f"sed -i 's/\\r//' {REMOTE_PROJECT}/scripts/*.sh {REMOTE_PROJECT}/start_all.sh 2>/dev/null && "
         f"chmod +x {REMOTE_PROJECT}/scripts/*.sh {REMOTE_PROJECT}/start_all.sh && echo OK",
         10),
        ("Install python-docx",
         "pip install python-docx==1.1.2 2>&1 | tail -3",
         60),
        ("Test category-aware doc loader",
         f"cd {REMOTE_PROJECT} && python3 -c '"
         "from core.documents import get_store; s=get_store(); "
         "cats=s.list_categories(); "
         "print(\"Categories:\", [(c[\\\"name\\\"], c[\\\"doc_count\\\"]) for c in cats]); "
         "if cats:\n"
         " top = s.retrieve(\"colis endommage\", category=cats[0][\\\"name\\\"], k=3); "
         "print(\"Top 3 in\", cats[0][\\\"name\\\"], \":\", [d.name for d in top])"
         "' 2>&1 | tail -15",
         30),
        # ── Try Gemma 4 download (will fall back to GemMaroc if it fails) ──
        ("Try downloading Gemma 4 26B (may fail if model not on HF)",
         f"export HF_TOKEN={HF_TOKEN} && cd {REMOTE_PROJECT} && "
         "timeout 600 bash scripts/download_models.sh gemma4 2>&1 | tail -20 || echo 'GEMMA4_FAILED'",
         700),
        ("Decide which model to serve",
         f"if [ -d /workspace/models/gemma4-26b-it ] && [ -f /workspace/models/gemma4-26b-it/config.json ]; then "
         f"  echo 'USING_GEMMA4'; sed -i 's/^VLLM_MODEL_NAME=.*/VLLM_MODEL_NAME=gemma4/' {REMOTE_PROJECT}/.env; "
         f"  TARGET=gemma4; "
         f"else "
         f"  echo 'GEMMA4_NOT_AVAILABLE_USING_GEMMAROC'; "
         f"  sed -i 's/^VLLM_MODEL_NAME=.*/VLLM_MODEL_NAME=gemmaroc/' {REMOTE_PROJECT}/.env; "
         f"  TARGET=gemmaroc; "
         f"fi && "
         f"sed -i 's|^VLLM_BASE_URL=.*|VLLM_BASE_URL=http://localhost:8002|' {REMOTE_PROJECT}/.env && "
         f"grep -E 'VLLM_(BASE_URL|MODEL_NAME)' {REMOTE_PROJECT}/.env && echo \"TARGET=$TARGET\" > /tmp/target.txt && cat /tmp/target.txt",
         15),
        ("Aggressive process + port cleanup",
         "pkill -9 -f 'vllm' 2>/dev/null; pkill -9 -f 'uvicorn' 2>/dev/null; "
         "for p in 8000 8002; do fuser -k $p/tcp 2>/dev/null; done; sleep 4; "
         "ss -tlnp 2>/dev/null | grep -E ':(8000|8002)' || echo 'ports free'",
         15),
        ("Start vLLM on port 8002",
         f"TARGET=$(cat /tmp/target.txt | cut -d= -f2) && echo \"Starting vLLM with $TARGET\" && "
         f"mkdir -p {REMOTE_PROJECT}/logs && rm -f {REMOTE_PROJECT}/logs/vllm_${{TARGET}}.log && "
         f"cd {REMOTE_PROJECT} && "
         f"nohup bash scripts/start_vllm.sh $TARGET > logs/vllm_${{TARGET}}.log 2>&1 & "
         f"echo VLLM_PID=$! && sleep 10 && "
         f"echo '--- log first 30 lines ---' && head -30 logs/vllm_${{TARGET}}.log",
         50),
        ("Wait for vLLM ready on port 8002 (up to 8 min)",
         f"TARGET=$(cat /tmp/target.txt | cut -d= -f2) && "
         "for i in $(seq 1 48); do "
         "  sleep 10; "
         "  if curl -sf http://localhost:8002/v1/models > /dev/null 2>&1; then "
         "    echo VLLM_READY_${i}; break; "
         "  fi; "
         "  if ! pgrep -f 'vllm' > /dev/null; then "
         f"    echo VLLM_DIED; tail -40 {REMOTE_PROJECT}/logs/vllm_${{TARGET}}.log; break; "
         "  fi; "
         f"  echo \"[$i/48] $(tail -1 {REMOTE_PROJECT}/logs/vllm_${{TARGET}}.log 2>/dev/null | head -c 180)\"; "
         "done",
         520),
        ("vLLM /v1/models",
         "curl -s http://localhost:8002/v1/models | python3 -m json.tool 2>&1 | head -20",
         15),
        # Build the web UI fresh so the new category dropdown is in dist/
        ("Rebuild web UI",
         f"cd {REMOTE_PROJECT}/web_test && npm run build 2>&1 | tail -10 && "
         f"ls -la dist/ | head -5",
         180),
        ("Start FastAPI",
         f"cd {REMOTE_PROJECT} && rm -f logs/api.log && "
         "nohup bash scripts/start_api.sh > logs/api.log 2>&1 & "
         "echo API_PID=$! && sleep 10 && tail -25 logs/api.log",
         30),
        ("Test /health",
         "curl -s http://localhost:8000/health | python3 -m json.tool 2>&1",
         15),
        ("Test /categories",
         "curl -s http://localhost:8000/categories | python3 -m json.tool 2>&1 | head -30",
         15),
        ("End-to-end chat test (Gestion category)",
         "rm -f /tmp/cj.txt && "
         "curl -s -c /tmp/cj.txt -X POST http://localhost:8000/auth/login "
         "-H 'Content-Type: application/json' -d '{\"password\":\"user1234\"}' "
         "| python3 -m json.tool | head -5; "
         "echo '--- chat: \"Comment gérer un colis endommagé ?\" (cat=Gestion) ---'; "
         "curl -s -b /tmp/cj.txt -X POST http://localhost:8000/chat "
         "-H 'Content-Type: application/json' "
         "-d '{\"message\":\"Comment gerer un colis endommage ?\",\"session_id\":\"t1\",\"category\":\"Gestion\"}' "
         "| python3 -m json.tool 2>&1 | head -40",
         180),
        ("Final summary",
         "echo '=== HEALTH ===' && curl -s http://localhost:8000/health | python3 -m json.tool; "
         f"echo '=== vLLM tail ===' && TARGET=$(cat /tmp/target.txt | cut -d= -f2) && tail -8 {REMOTE_PROJECT}/logs/vllm_${{TARGET}}.log; "
         f"echo '=== API tail ===' && tail -8 {REMOTE_PROJECT}/logs/api.log",
         15),
    ]

    for label, cmd, timeout in STEPS:
        run(shell, label, cmd, timeout)

    shell.close()
    client.close()
    print("\n\n=== DEPLOYMENT COMPLETE ===")
    print("Open http://localhost:8000   →  password: user1234")
    print("Make sure SSH tunnel is running:")
    print("  ssh -L 8000:localhost:8000 -L 8002:localhost:8002 runpod2")


if __name__ == "__main__":
    main()
