#!/usr/bin/env python3
"""
Pull a remote directory from the RunPod box.

RunPod's gateway rejects non-interactive SSH exec and breaks scp/SFTP; this uses a
Paramiko **PTY shell**: create a tarball on the pod, stream base64, decode, extract.

Example:
  python scripts/fetch_pod_tar.py
  python scripts/fetch_pod_tar.py --remote /workspace/gemma-test-backup-202605051228/data/documents/procedures
"""
from __future__ import annotations

import argparse
import base64
import binascii
import io
import os
import re
import sys
import tarfile
import time
from pathlib import Path

import paramiko

HOST = "ssh.runpod.io"
USER = "l8lnmi6ofx0tpz-64411278"
KEY_PATH = os.path.expanduser("~/.ssh/id_ed25519")
ANSI_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

REPO_ROOT = Path(__file__).resolve().parent.parent


def _recv_until_marker(shell: paramiko.Channel, end: bytes, timeout: float = 900.0) -> bytes:
    buf = b""
    t_end = time.time() + timeout
    while time.time() < t_end:
        if shell.recv_ready():
            buf += shell.recv(65536)
            if end in buf:
                return buf
        else:
            time.sleep(0.1)
    raise TimeoutError(f"timeout after {len(buf)} bytes")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--remote",
        default="/workspace/gemma-test/data/documents/procedures",
        help="Absolute path to directory on the pod",
    )
    parser.add_argument(
        "--into",
        default=str(REPO_ROOT / "data" / "documents"),
        help="Local parent directory for extraction",
    )
    args = parser.parse_args()
    remote = args.remote.rstrip("/")
    rparent, rname = os.path.split(remote)
    if not rname:
        print("remote must be a directory path", file=sys.stderr)
        return 1

    dest = Path(args.into).resolve()
    dest.mkdir(parents=True, exist_ok=True)
    tgz = "/tmp/gemma_fetch_proc.tgz"

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"Connecting {USER}@{HOST} (PTY shell)...")
    client.connect(
        HOST,
        username=USER,
        key_filename=KEY_PATH,
        look_for_keys=False,
        allow_agent=False,
    )
    shell = client.invoke_shell(term="xterm", width=200, height=50)
    time.sleep(2)
    while shell.recv_ready():
        shell.recv(65536)

    shell.send(f"tar czf {tgz} -C {rparent} {rname} && ls -la {tgz}\r")
    time.sleep(4)
    while shell.recv_ready():
        shell.recv(65536)

    b64file = "/tmp/gemma_fetch_proc.b64"
    shell.send(
        f"(base64 -w0 {tgz} 2>/dev/null || openssl base64 -A -in {tgz}) > {b64file} "
        f"&& wc -c {b64file}\r"
    )
    time.sleep(4)
    while shell.recv_ready():
        shell.recv(65536)

    # Single shell line (after stty -echo) avoids racing a separate printf after cat.
    shell.send("stty -echo\r")
    time.sleep(0.4)
    while shell.recv_ready():
        shell.recv(65536)
    shell.send(
        f"cat {b64file} && printf '\\nGEMMA_B64_END\\n' && stty echo\r"
    )

    print("Downloading (base64 stream)...")
    raw = _recv_until_marker(shell, b"GEMMA_B64_END")
    shell.close()
    client.close()

    text = ANSI_RE.sub("", raw.decode("utf-8", "replace"))
    if "GEMMA_B64_END" not in text:
        print(text[:2500], file=sys.stderr)
        print("--- no GEMMA_B64_END in output", file=sys.stderr)
        return 2

    mid = text.split("GEMMA_B64_END", 1)[0]
    parts = re.findall(r"[A-Za-z0-9+/=]+", mid)
    if not parts:
        print("No base64 payload found in stream.", file=sys.stderr)
        return 2
    b64 = max(parts, key=len)
    b64 = re.sub(r"[^A-Za-z0-9+/=]", "", b64)
    pad = (-len(b64)) % 4
    if pad:
        b64 += "=" * pad

    try:
        binary = base64.b64decode(b64, validate=False)
    except binascii.Error as e:
        print(f"base64 decode failed: {e}", file=sys.stderr)
        return 3

    if len(binary) < 200 or binary[:2] != b"\x1f\x8b":
        print(
            f"Not a gzip tarball ({len(binary)} bytes). Head: {binary[:24]!r}",
            file=sys.stderr,
        )
        return 4

    tf = tarfile.open(fileobj=io.BytesIO(binary), mode="r:gz")
    try:
        try:
            tf.extractall(path=str(dest), filter="data")
        except TypeError:
            tf.extractall(path=str(dest))
    finally:
        tf.close()

    print(f"Extracted under {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
