import base64
import paramiko
import time
import os
import re

HOST = "ssh.runpod.io"
USER = "l8lnmi6ofx0tpz-64411278"
KEY_PATH = os.path.expanduser("~/.ssh/id_ed25519")

def upload_zip():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, key_filename=KEY_PATH, look_for_keys=False, allow_agent=False)
    
    shell = client.invoke_shell(term="xterm", width=200, height=50)
    shell.settimeout(0.5)
    time.sleep(2)
    while shell.recv_ready(): shell.recv(8192)

    def run_cmd(cmd):
        shell.send(cmd + "\r")
        time.sleep(0.5)
        while shell.recv_ready(): shell.recv(8192)

    run_cmd("rm -f /workspace/gemma-test/docs.b64")
    
    with open("docs.zip", "rb") as f:
        b64_data = base64.b64encode(f.read()).decode('ascii')
    
    chunk_size = 10000
    total_chunks = len(b64_data) // chunk_size + 1
    
    for i in range(total_chunks):
        chunk = b64_data[i*chunk_size:(i+1)*chunk_size]
        if chunk:
            print(f"Uploading chunk {i+1}/{total_chunks}...")
            # Use printf to append without echo issues
            shell.send(f"printf '%s' '{chunk}' >> /workspace/gemma-test/docs.b64\r")
            time.sleep(0.3)
            while shell.recv_ready(): shell.recv(8192)
            
    print("Decoding and unzipping...")
    run_cmd("cd /workspace/gemma-test && base64 -d docs.b64 > docs.zip")
    run_cmd("cd /workspace/gemma-test && mkdir -p data/documents && unzip -o docs.zip -d data/documents")
    run_cmd("rm -f /workspace/gemma-test/docs.b64 /workspace/gemma-test/docs.zip")
    
    print("Done!")
    shell.close()
    client.close()

if __name__ == "__main__":
    upload_zip()
