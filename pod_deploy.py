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

# Force UTF-8 stdout so vLLM/hf_transfer progress chars don't crash on cp1252
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

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
    """Upload via base64 in paramiko shell (RunPod gateway blocks SCP/SFTP/exec)."""
    print("\n" + "="*70)
    print(">>> Uploading data/documents/ via base64-over-shell")
    print("="*70)
    if not LOCAL_DOCS.is_dir():
        print(f"FATAL: {LOCAL_DOCS} not found")
        sys.exit(1)

    import base64

    # Build tarball of only the 'procedures' subfolder
    LOCAL_PROCEDURES = LOCAL_DOCS / "procedures"
    if not LOCAL_PROCEDURES.is_dir():
        print(f"FATAL: {LOCAL_PROCEDURES} not found — put your .docx files in data/documents/procedures/")
        sys.exit(1)
    local_tar = LOCAL_ROOT / "_docs_upload.tar.gz"
    if local_tar.exists():
        local_tar.unlink()
    print(f"Building tarball of procedures/ ({len(list(LOCAL_PROCEDURES.glob('*.docx')))} docs): {local_tar}")
    proc = subprocess.run(
        ["tar", "-czf", str(local_tar), "-C", str(LOCAL_DOCS), "procedures"],
        capture_output=True, text=True, timeout=60,
    )
    if proc.returncode != 0:
        print("tar failed:", proc.stderr)
        sys.exit(1)

    raw = local_tar.read_bytes()
    b64 = base64.b64encode(raw).decode("ascii")
    print(f"Tarball: {len(raw)/1024:.1f} KB → base64 {len(b64)/1024:.1f} KB")
    local_tar.unlink(missing_ok=True)

    # Open dedicated SSH session for upload
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=HOST, username=USER, key_filename=KEY_PATH,
        timeout=30, look_for_keys=False, allow_agent=False,
    )
    shell = client.invoke_shell(term="xterm-256color", width=200, height=40)
    shell.settimeout(300)
    time.sleep(2)
    wait_for_prompt(shell, timeout=15)

    # Wipe only subdirectory category folders (keep flat dir itself), then prepare receive
    shell.send(f"mkdir -p {REMOTE_DOCS} && find {REMOTE_DOCS} -mindepth 1 -maxdepth 1 -type d -exec rm -rf {{}} + && rm -f /tmp/docs.b64 && echo READY\n")
    wait_for_prompt(shell, timeout=15)

    # PTY canonical mode limits line input to ~4KB. Use 3000 to be safe.
    chunk_size = 3000
    total_chunks = (len(b64) + chunk_size - 1) // chunk_size
    print(f"Streaming {total_chunks} chunks...")

    def drain(shell, briefly=True):
        """Drain pending shell output without blocking long."""
        end = time.time() + (0.05 if briefly else 2.0)
        while time.time() < end:
            if shell.recv_ready():
                shell.recv(65536)
            else:
                time.sleep(0.01)

    for i in range(total_chunks):
        chunk = b64[i*chunk_size:(i+1)*chunk_size]
        # base64 alphabet has no shell-special chars; safe inside single quotes
        shell.send(f"printf '%s' '{chunk}' >> /tmp/docs.b64\n")
        # Brief drain every chunk; longer every 50 to prevent backpressure
        if (i+1) % 50 == 0:
            drain(shell, briefly=False)
            print(f"  Sent chunk {i+1}/{total_chunks}")
        else:
            drain(shell, briefly=True)
    drain(shell, briefly=False)
    print(f"  Sent chunk {total_chunks}/{total_chunks}")

    # Decode + extract procedures/ into REMOTE_DOCS
    print("Decoding + extracting on pod...")
    shell.send(
        f"base64 -d /tmp/docs.b64 > /tmp/docs.tar.gz && "
        f"tar xzf /tmp/docs.tar.gz -C {REMOTE_DOCS} && "
        f"rm -f /tmp/docs.b64 /tmp/docs.tar.gz && "
        f"find {REMOTE_DOCS} -name '*.docx' | wc -l && echo UPLOAD_OK\n"
    )
    out = wait_for_prompt(shell, timeout=60)
    shell.close()
    client.close()
    if "UPLOAD_OK" not in out:
        print("Upload verification failed!")
        sys.exit(1)
    print("✓ Upload complete")


def main():
    skip_upload = "--skip-upload" in sys.argv
    # ── Step 0: Upload docs (skip with --skip-upload if already uploaded) ──
    if skip_upload:
        print(">>> Skipping doc upload (--skip-upload)")
    else:
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
        ("Pull latest code (origin/main)",
         f"cd {REMOTE_PROJECT} && git fetch origin main && "
         "git reset --hard FETCH_HEAD && "
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
         f"cd {REMOTE_PROJECT} && python3 << 'PYEOF'\n"
         "from core.documents import get_store\n"
         "s = get_store()\n"
         "cats = s.list_categories()\n"
         "print('Categories:', [(c['name'], c['doc_count']) for c in cats])\n"
         "if cats:\n"
         "    top = s.retrieve('colis endommage', category=cats[0]['name'], k=3)\n"
         "    print('Top 3 in', cats[0]['name'], ':', [d.name for d in top])\n"
         "PYEOF",
         30),
        ("Select model (gemma4-26b-it if present, else GemMaroc-27b-it fallback)",
         f"if [ -d /workspace/models/gemma4-26b-it ]; then "
         f"  echo 'Using gemma4-26b-it' && "
         f"  sed -i 's/^VLLM_MODEL_NAME=.*/VLLM_MODEL_NAME=gemma4-26b-it/' {REMOTE_PROJECT}/.env && "
         f"  echo TARGET=gemma4 > /tmp/target.txt; "
         f"elif [ -d /workspace/models/GemMaroc-27b-it ]; then "
         f"  echo 'gemma4 not found — using GemMaroc-27b-it' && "
         f"  sed -i 's/^VLLM_MODEL_NAME=.*/VLLM_MODEL_NAME=GemMaroc-27b-it/' {REMOTE_PROJECT}/.env && "
         f"  echo TARGET=gemmaroc > /tmp/target.txt; "
         f"else "
         f"  echo 'ERROR: neither gemma4-26b-it nor GemMaroc-27b-it found in /workspace/models/' && "
         f"  ls /workspace/models/ && exit 1; "
         f"fi && "
         f"sed -i 's|^VLLM_BASE_URL=.*|VLLM_BASE_URL=http://localhost:8002|' {REMOTE_PROJECT}/.env && "
         f"grep -E 'VLLM_(BASE_URL|MODEL_NAME)' {REMOTE_PROJECT}/.env && "
         f"cat /tmp/target.txt",
         15),
        ("Aggressive process + port cleanup",
         "pkill -9 -f 'serve_gemma4' 2>/dev/null; pkill -9 -f 'start_vllm' 2>/dev/null; pkill -9 -f 'uvicorn' 2>/dev/null; "
         # Also kill any stale python3 processes holding GPU memory (e.g. from OOM crashes)
         "pkill -9 -f 'serve_gemma4.py' 2>/dev/null; "
         "for p in 8000 8002; do fuser -k $p/tcp 2>/dev/null; done; sleep 6; "
         "echo '--- GPU after cleanup ---' && nvidia-smi --query-gpu=index,memory.used --format=csv,noheader; "
         "ss -tlnp 2>/dev/null | grep -E ':(8000|8002)' || echo 'ports free'",
         20),
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
         "  if ! pgrep -f 'serve_gemma4' > /dev/null; then "
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
        ("End-to-end chat test (first available category)",
         "rm -f /tmp/cj.txt && "
         "curl -s -c /tmp/cj.txt -X POST http://localhost:8000/auth/login "
         "-H 'Content-Type: application/json' -d '{\"password\":\"user1234\"}' "
         "| python3 -m json.tool | head -5; "
         "FIRST_CAT=$(curl -s http://localhost:8000/categories | "
         "python3 -c \"import sys,json; cats=json.load(sys.stdin)['categories']; print(cats[0]['name'] if cats else 'procedures')\"); "
         "echo \"--- chat test (category=$FIRST_CAT) ---\"; "
         "curl -s -b /tmp/cj.txt -X POST http://localhost:8000/chat "
         "-H 'Content-Type: application/json' "
         "-d \"{\\\"message\\\":\\\"Comment fonctionne cette procedure ?\\\",\\\"session_id\\\":\\\"t1\\\",\\\"category\\\":\\\"$FIRST_CAT\\\"}\" "
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
