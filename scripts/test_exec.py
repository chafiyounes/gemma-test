import paramiko
import os
from pathlib import Path

HOST = "ssh.runpod.io"
USER = "l8lnmi6ofx0tpz-64411278"
KEY_PATH = os.path.expanduser("~/.ssh/id_ed25519")

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, key_filename=KEY_PATH, look_for_keys=False, allow_agent=False)

try:
    stdin, stdout, stderr = client.exec_command("echo HELLO > /workspace/gemma-test/hello.txt")
    print("STDOUT:", stdout.read().decode())
    print("STDERR:", stderr.read().decode())
except Exception as e:
    print("Failed:", e)

client.close()
