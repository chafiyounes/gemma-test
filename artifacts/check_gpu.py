"""GPU diagnostic for RunPod pod."""
import paramiko
import time
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

KEY_PATH = r"C:\Users\pc gamer\.ssh\id_ed25519"
HOST = "ssh.runpod.io"
USER = "xkebko0395sada-6441173b"
PROMPT_RE = re.compile(r"[#$]\s*$")

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, key_filename=KEY_PATH, timeout=30, look_for_keys=False, allow_agent=False)
shell = client.invoke_shell(term="xterm-256color", width=220, height=50)
shell.settimeout(30)
time.sleep(2)


def recv(timeout=30):
    buf = ""
    t = time.time() + timeout
    while time.time() < t:
        if shell.recv_ready():
            buf += shell.recv(8192).decode("utf-8", "replace")
        elif buf.rstrip() and PROMPT_RE.search(buf.rstrip()[-5:]):
            break
        else:
            time.sleep(0.1)
    return buf


recv()

cmds = [
    ("nvidia-smi", "nvidia-smi --query-gpu=index,name,memory.total,memory.used,memory.free --format=csv"),
    ("cuda device count", "python3 -c 'import torch; n=torch.cuda.device_count(); print(\"CUDA devices:\", n); [print(i, torch.cuda.get_device_properties(i).name, torch.cuda.get_device_properties(i).total_memory//1024//1024, \"MB total\") for i in range(n)]'"),
    ("tail vllm log", "tail -20 /workspace/gemma-test/logs/vllm_gemma4.log"),
    ("check bitsandbytes", "python3 -c 'import bitsandbytes; print(bitsandbytes.__version__)' 2>&1 || echo 'NOT INSTALLED'"),
    ("free memory per gpu", "python3 -c 'import torch; [print(f\"cuda:{i} free: {torch.cuda.mem_get_info(i)[0]//1024//1024} MB / {torch.cuda.mem_get_info(i)[1]//1024//1024} MB\") for i in range(torch.cuda.device_count())]'"),
]

for label, cmd in cmds:
    print(f"\n{'='*60}\n>>> {label}\n{'='*60}")
    shell.send(cmd + "\n")
    print(recv())

shell.close()
client.close()
