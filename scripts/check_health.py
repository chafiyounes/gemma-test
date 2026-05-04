import paramiko
import time
import os
import sys
import re

HOST = "ssh.runpod.io"
USER = "l8lnmi6ofx0tpz-64411278"
KEY_PATH = os.path.expanduser("~/.ssh/id_ed25519")

def strip_ansi(text):
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

def check_logs():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, key_filename=KEY_PATH, look_for_keys=False, allow_agent=False)
    shell = client.invoke_shell(term="xterm")
    time.sleep(2)
    while shell.recv_ready(): shell.recv(8192)

    cmds = [
        "tail -n 50 /workspace/gemma-test/logs/vllm.log"
    ]
    
    for cmd in cmds:
        print(f"\n--- {cmd} ---")
        shell.send(cmd + "\r")
        time.sleep(3)
        if shell.recv_ready():
            out = shell.recv(8192).decode("utf-8", "replace")
            print(strip_ansi(out).encode('ascii', 'ignore').decode())

    shell.close()
    client.close()

if __name__ == "__main__":
    check_logs()
