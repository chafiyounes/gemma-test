"""Quick inference speed check via SSH."""
import paramiko, time, sys

KEY_PATH = r"C:\Users\pc gamer\.ssh\id_ed25519"
HOST = "ssh.runpod.io"
USER = "xkebko0395sada-6441173b"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, key_filename=KEY_PATH, timeout=30)
shell = client.invoke_shell(width=220, height=60)
time.sleep(3)
shell.recv(20000)  # drain banner

# 1. Check vLLM log tail (includes quant mode + any previous generated-tokens lines)
shell.send("tail -20 /workspace/gemma-test/logs/vllm_gemma4.log\n")
time.sleep(4)
out = b""
while shell.recv_ready():
    out += shell.recv(8192)
    time.sleep(0.2)
print("=== vLLM log tail ===")
print(out.decode("utf-8", errors="replace"))

# 2. Run a timed inference request
print("=== Sending inference request ===")
curl_cmd = (
    'curl -s -m 120 -X POST http://localhost:8002/v1/chat/completions '
    '-H "Content-Type: application/json" '
    '-d \'{"model":"gemma4-26b-it","messages":[{"role":"user","content":"Bonjour, comment vas-tu?"}],"max_tokens":40}\' ; echo DONE\n'
)
shell.send(curl_cmd)

# wait up to 110s
deadline = time.time() + 110
collected = b""
while time.time() < deadline:
    time.sleep(2)
    while shell.recv_ready():
        collected += shell.recv(8192)
    if b"DONE" in collected:
        break

print(collected.decode("utf-8", errors="replace"))

# 3. Check the "Generated X tokens in Ys" log line that the server just wrote
time.sleep(2)
shell.send("grep 'Generated' /workspace/gemma-test/logs/vllm_gemma4.log | tail -3\n")
time.sleep(4)
out2 = b""
while shell.recv_ready():
    out2 += shell.recv(8192)
    time.sleep(0.2)
print("=== Generated timing lines ===")
print(out2.decode("utf-8", errors="replace"))

client.close()
