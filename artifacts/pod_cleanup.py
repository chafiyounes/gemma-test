"""Pod prep: clean disk, remove old models, download Gemma 4 26B (xet disabled)."""
import os, time, re, sys
from pathlib import Path
import paramiko

# Force UTF-8 stdout to handle hf_transfer progress bars
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HOST = "ssh.runpod.io"
USER = "xkebko0395sada-6441173b"
KEY_PATH = str(Path.home() / ".ssh" / "id_ed25519")
PROMPT_RE = re.compile(r"[#$]\s*$")

HF_TOKEN = os.environ.get("HF_TOKEN")
if not HF_TOKEN:
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("HF_TOKEN="):
                HF_TOKEN = line.split("=", 1)[1].strip().strip('"').strip("'")
                break
if not HF_TOKEN:
    print("FATAL: HF_TOKEN not in env or .env"); sys.exit(1)


def wait_for_prompt(shell, timeout=120):
    buf = ""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if shell.recv_ready():
            chunk = shell.recv(65536).decode("utf-8", errors="replace")
            buf += chunk
            sys.stdout.write(chunk); sys.stdout.flush()
            tail = buf.splitlines()[-1] if buf.splitlines() else ""
            if PROMPT_RE.search(tail[-5:]):
                return buf
        else:
            time.sleep(0.1)
    return buf


def run(shell, cmd, timeout=120):
    print(f"\n>>> {cmd[:140]}{'...' if len(cmd) > 140 else ''}")
    shell.send(cmd + "\n")
    return wait_for_prompt(shell, timeout)


client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(hostname=HOST, username=USER, key_filename=KEY_PATH,
               timeout=30, look_for_keys=False, allow_agent=False)
shell = client.invoke_shell(term="xterm-256color", width=220, height=50)
shell.settimeout(3600)
time.sleep(2)
wait_for_prompt(shell, 15)

run(shell, "df -h /workspace /root /tmp 2>&1")
run(shell, "du -sh /workspace/models/* 2>/dev/null; echo ---; du -sh ~/.cache/huggingface 2>/dev/null")
run(shell, "pkill -9 -f 'vllm' 2>/dev/null; pkill -9 -f 'uvicorn' 2>/dev/null; sleep 2; echo killed")
run(shell, "rm -rf /workspace/models/GemMaroc-27b-it 2>/dev/null; "
           "rm -rf /workspace/models/gemma4* 2>/dev/null; "
           "rm -rf ~/.cache/huggingface/hub/models--google--gemma-4-26B-A4B-it 2>/dev/null; "
           "rm -rf ~/.cache/huggingface/xet 2>/dev/null; "
           "rm -rf ~/.cache/huggingface/hub/.locks 2>/dev/null; "
           "find ~/.cache/huggingface -name '*.incomplete' -delete 2>/dev/null; "
           "find ~/.cache/huggingface -name '*.lock' -delete 2>/dev/null; "
           "rm -rf /tmp/*.tar.gz /tmp/docs.b64 /tmp/*.b64 2>/dev/null; "
           "echo CLEANED")
run(shell, "df -h /workspace /root 2>&1")

run(shell, "pip install -U 'huggingface_hub[hf_transfer]' hf_transfer 2>&1 | tail -5", timeout=180)

# Probe: exists? gated?
run(shell, f"export HF_TOKEN={HF_TOKEN} && "
           "python3 -c \"from huggingface_hub import HfApi; "
           "info = HfApi().model_info('google/gemma-4-26B-A4B-it'); "
           "print('OK', info.modelId, 'gated=', info.gated, 'siblings=', len(info.siblings))\" 2>&1 | tail -5", timeout=60)

# Write the download script to a file (avoids quoting hell), then run via nohup so it survives if local SSH drops
run(shell, "cat > /tmp/dl_gemma4.py <<'PYEOF'\n"
           "import os\n"
           "os.environ['HF_HUB_DISABLE_XET'] = '1'\n"
           "os.environ['HF_HUB_ENABLE_HF_TRANSFER'] = '1'\n"
           "from huggingface_hub import snapshot_download\n"
           "p = snapshot_download(\n"
           "    repo_id='google/gemma-4-26B-A4B-it',\n"
           "    local_dir='/workspace/models/gemma4-26b-it',\n"
           "    max_workers=8,\n"
           "    ignore_patterns=['*.gguf','*.bin','original/*','*consolidated*'],\n"
           ")\n"
           "print('DONE', p)\n"
           "PYEOF\n"
           "echo SCRIPT_WRITTEN")

# Launch in background, log to file
run(shell, f"export HF_TOKEN={HF_TOKEN} && "
           "rm -f /tmp/gemma4_dl.log && "
           "nohup python3 /tmp/dl_gemma4.py > /tmp/gemma4_dl.log 2>&1 & "
           "echo DL_PID=$! && sleep 3 && tail -5 /tmp/gemma4_dl.log")

# Poll until done or fail (max ~50 min for 50GB)
run(shell, "for i in $(seq 1 100); do "
           "  sleep 30; "
           "  if grep -q '^DONE ' /tmp/gemma4_dl.log 2>/dev/null; then echo DOWNLOAD_OK; break; fi; "
           "  if grep -qE 'Error|Traceback|raise ' /tmp/gemma4_dl.log 2>/dev/null; then echo DOWNLOAD_FAIL; tail -20 /tmp/gemma4_dl.log; break; fi; "
           "  if ! pgrep -f 'dl_gemma4.py' > /dev/null; then echo DOWNLOAD_DIED; tail -20 /tmp/gemma4_dl.log; break; fi; "
           "  SZ=$(du -sh /workspace/models/gemma4-26b-it 2>/dev/null | cut -f1); "
           "  echo \"[$i/100] size=$SZ\"; "
           "done", timeout=3600)

run(shell, "ls -lah /workspace/models/gemma4-26b-it/ && "
           "du -sh /workspace/models/gemma4-26b-it && "
           "test -f /workspace/models/gemma4-26b-it/config.json && echo MODEL_OK")
run(shell, "df -h /workspace /root")

shell.close(); client.close()
print("\n=== POD PREP DONE ===")
