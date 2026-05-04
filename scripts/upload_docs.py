import os
import base64
import paramiko
import time
from pathlib import Path
import re

HOST = "ssh.runpod.io"
USER = "l8lnmi6ofx0tpz-64411278"
KEY_PATH = os.path.expanduser("~/.ssh/id_ed25519")

LOCAL_DOCS_DIR = Path("C:/Users/pc gamer/OneDrive/Desktop/full project/gemma-test/data/documents")

def strip_ansi(text):
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

def upload_via_pty():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, key_filename=KEY_PATH, look_for_keys=False, allow_agent=False)
    
    shell = client.invoke_shell(term="xterm", width=200, height=50)
    shell.settimeout(0.5)
    time.sleep(2)
    while shell.recv_ready(): shell.recv(8192)

    def run_cmd(cmd):
        shell.send(cmd + "\r")
        time.sleep(1)
        buf = b""
        while shell.recv_ready():
            buf += shell.recv(8192)

    print("Creating remote directories...")
    run_cmd("mkdir -p /workspace/gemma-test/data/documents/procedures")
    
    for root, dirs, files in os.walk(LOCAL_DOCS_DIR):
        for file in files:
            if file.endswith(".docx"):
                local_path = os.path.join(root, file)
                rel_path = os.path.relpath(local_path, LOCAL_DOCS_DIR)
                # handle windows paths
                rel_path = rel_path.replace("\\", "/")
                remote_path = f"/workspace/gemma-test/data/documents/{rel_path}"
                
                print(f"Uploading {rel_path}...")
                with open(local_path, "rb") as f:
                    b64_data = base64.b64encode(f.read()).decode('ascii')
                
                # We'll write a small python script on the remote to decode it
                py_script = f"""
import base64
import os
os.makedirs(os.path.dirname("{remote_path}"), exist_ok=True)
with open("{remote_path}", "wb") as f:
    f.write(base64.b64decode("{b64_data}"))
"""
                run_cmd(f"cat << 'EOF' > /tmp/upload.py\n{py_script}\nEOF\n")
                run_cmd("python3 /tmp/upload.py")
                
    print("Upload complete.")
    shell.close()
    client.close()

if __name__ == "__main__":
    upload_via_pty()
