"""Run commands on the RunPod pod via paramiko SSH (PTY-aware)."""
import paramiko, time, os, sys, re

HOST = "ssh.runpod.io"
USER = "l8lnmi6ofx0tpz-64411278"
KEY  = os.path.expanduser("~/.ssh/id_ed25519")
ANSI = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

def run(cmds, wait=5):
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username=USER, key_filename=KEY, look_for_keys=False, allow_agent=False)
    sh = c.invoke_shell(term="xterm", width=200, height=50)
    time.sleep(2)
    while sh.recv_ready(): sh.recv(8192)
    for cmd in cmds:
        sh.send(cmd + "\r")
        time.sleep(wait)
        buf = b""
        while sh.recv_ready():
            buf += sh.recv(8192)
        out = ANSI.sub("", buf.decode("utf-8","replace"))
        print(out.encode("ascii","replace").decode())
    sh.close(); c.close()

if __name__ == "__main__":
    run(sys.argv[1:] if len(sys.argv) > 1 else ["echo CONNECTED"])
