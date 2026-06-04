"""Shared RunPod SSH settings for Paramiko scripts.

Reads RUNPOD_SSH_HOST, RUNPOD_SSH_USER, RUNPOD_SSH_KEY from the environment.
Also loads those keys from repo-root ``.env`` if present (never commit real values).
"""
from __future__ import annotations

import os
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_ENV_FILE = _REPO_ROOT / ".env"


def _load_env_file() -> None:
    if not _ENV_FILE.is_file():
        return
    for line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        if key.startswith("RUNPOD_SSH_") and key not in os.environ:
            os.environ[key] = val.strip().strip('"').strip("'")


_load_env_file()

HOST: str = os.environ.get("RUNPOD_SSH_HOST", "ssh.runpod.io")
USER: str = os.environ.get("RUNPOD_SSH_USER", "dvy5w58nwyz155-64411299")
KEY_PATH: str = os.environ.get("RUNPOD_SSH_KEY", os.path.expanduser("~/.ssh/id_ed25519"))
