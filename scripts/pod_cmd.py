"""Run commands on the RunPod pod via paramiko SSH (PTY-aware)."""
import paramiko, time, os, sys, re
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.runpod_ssh import HOST, KEY_PATH as KEY, USER
ANSI = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

def _connect_shell():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username=USER, key_filename=KEY, look_for_keys=False, allow_agent=False)
    sh = c.invoke_shell(term="xterm", width=200, height=50)
    time.sleep(2)
    while sh.recv_ready():
        sh.recv(8192)
    return c, sh


def run_remote(cmd: str, *, wait: float = 5.0) -> str:
    """Run one shell command on the pod; return decoded output (no echo to stdout)."""
    c, sh = _connect_shell()
    try:
        sh.send(cmd + "\n")
        time.sleep(wait)
        buf = b""
        while sh.recv_ready():
            buf += sh.recv(8192)
        return ANSI.sub("", buf.decode("utf-8", "replace"))
    finally:
        sh.close()
        c.close()


def run(cmds, wait=5):
    c, sh = _connect_shell()
    try:
        for cmd in cmds:
            sh.send(cmd + "\r")
            time.sleep(float(wait))
            buf = b""
            while sh.recv_ready():
                buf += sh.recv(8192)
            out = ANSI.sub("", buf.decode("utf-8", "replace"))
            print(out.encode("ascii", "replace").decode())
    finally:
        sh.close()
        c.close()

if __name__ == "__main__":
    argv = sys.argv[1:]
    wait = 5.0
    if len(argv) >= 2 and argv[0] == "--wait":
        wait = float(argv[1])
        argv = argv[2:]
    if not argv:
        argv = ["echo CONNECTED"]
    run(argv, wait=wait)
