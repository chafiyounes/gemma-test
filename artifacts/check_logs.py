import paramiko, time, re, sys
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

KEY_PATH = r'C:\Users\pc gamer\.ssh\id_ed25519'
HOST = 'ssh.runpod.io'
USER = 'xkebko0395sada-6441173b'
PROMPT_RE = re.compile(r'[#$]\s*$')

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, key_filename=KEY_PATH, timeout=30, look_for_keys=False, allow_agent=False)
shell = client.invoke_shell(term='xterm-256color', width=220, height=50)
shell.settimeout(30)
time.sleep(2)

def recv(timeout=25):
    buf = ''
    t = time.time() + timeout
    while time.time() < t:
        if shell.recv_ready():
            buf += shell.recv(8192).decode('utf-8', 'replace')
        elif buf.rstrip() and PROMPT_RE.search(buf.rstrip()[-5:]):
            break
        else:
            time.sleep(0.1)
    return buf

recv()  # drain banner

cmds = [
    'python3 -c "import transformers; print(transformers.__version__)"',
    'python3 -c "from transformers import AutoTokenizer; t=AutoTokenizer.from_pretrained(\'/workspace/models/gemma4-26b-it\'); import inspect; print(list(inspect.signature(t.apply_chat_template).parameters.keys()))"',
    'tail -60 /workspace/gemma-test/logs/vllm_gemma4.log',
    'tail -30 /workspace/gemma-test/logs/api.log',
    # Quick chat test directly against inference server
    'curl -s -X POST http://localhost:8002/v1/chat/completions -H "Content-Type: application/json" -d \'{"messages":[{"role":"user","content":"Dis bonjour en une phrase."}],"max_tokens":50}\' | python3 -m json.tool 2>&1 | head -20',
]

for c in cmds:
    print(f'\n{"="*60}\n>>> {c[:80]}\n{"="*60}')
    shell.send(c + '\n')
    out = recv(60)
    print(out)

shell.close()
client.close()
