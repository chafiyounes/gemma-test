#!/usr/bin/env python3
"""
Recycle a RunPod over the REST API so GPUs release VRAM — without using the web UI.

Run from your **laptop** (the SSH session will die when the pod stops).

Environment:
  RUNPOD_API_KEY   — bearer token (RunPod account → API keys)
  RUNPOD_POD_ID    — pod id from the RunPod dashboard (e.g. ``xedezhzb9la3ye``)

Docs: https://docs.runpod.io/api-reference/pods/POST/pods/podId/stop

Usage:
  python scripts/runpod_recycle_pod.py
  python scripts/runpod_recycle_pod.py --pod-id abc123
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

API_BASE = "https://rest.runpod.io/v1"


def _request(
    method: str,
    path: str,
    *,
    api_key: str,
    body: dict | None = None,
    timeout: float = 120.0,
) -> tuple[int, str]:
    url = f"{API_BASE}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            return resp.status, raw
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        return exc.code, raw


def _get_pod(api_key: str, pod_id: str) -> dict:
    code, text = _request("GET", f"/pods/{pod_id}", api_key=api_key)
    if code != 200:
        raise RuntimeError(f"GET /pods/{pod_id} failed HTTP {code}: {text[:800]}")
    return json.loads(text)


def main() -> int:
    parser = argparse.ArgumentParser(description="RunPod stop + start via REST API")
    parser.add_argument("--pod-id", default=os.environ.get("RUNPOD_POD_ID", "").strip())
    parser.add_argument(
        "--wait-running",
        type=int,
        default=0,
        metavar="SEC",
        help="After start, poll GET /pods until RUNNING or timeout seconds (0 = skip)",
    )
    args = parser.parse_args()

    api_key = os.environ.get("RUNPOD_API_KEY", "").strip()
    pod_id = args.pod_id
    if not api_key or not pod_id:
        print(
            "Set RUNPOD_API_KEY and RUNPOD_POD_ID (or pass --pod-id).",
            file=sys.stderr,
        )
        return 2

    print(f"Stopping pod {pod_id!r} …")
    code, text = _request("POST", f"/pods/{pod_id}/stop", api_key=api_key)
    if code not in (200, 201, 204):
        print(f"Stop failed HTTP {code}: {text[:1200]}", file=sys.stderr)
        return 1

    # Wait until the pod is no longer RUNNING (driver teardown).
    for i in range(36):
        time.sleep(5)
        try:
            pod = _get_pod(api_key, pod_id)
        except RuntimeError as e:
            print(f"  poll {i + 1}/36: {e}", file=sys.stderr)
            continue
        status = str(pod.get("desiredStatus", "")).upper()
        print(f"  desiredStatus={status!r}")
        if status and status != "RUNNING":
            break
    else:
        print(
            "Pod still reports RUNNING after ~3 min — check dashboard; "
            "continuing with start anyway.",
            file=sys.stderr,
        )

    print(f"Starting pod {pod_id!r} …")
    code, text = _request("POST", f"/pods/{pod_id}/start", api_key=api_key)
    if code not in (200, 201, 204):
        print(f"Start failed HTTP {code}: {text[:1200]}", file=sys.stderr)
        return 1

    if args.wait_running > 0:
        deadline = time.time() + args.wait_running
        while time.time() < deadline:
            pod = _get_pod(api_key, pod_id)
            status = str(pod.get("desiredStatus", "")).upper()
            if status == "RUNNING":
                print("Pod is RUNNING.")
                break
            time.sleep(5)
        else:
            print("Timeout waiting for RUNNING — check dashboard.", file=sys.stderr)

    print(
        "\nNext: SSH into the pod, then:\n"
        "  cd /workspace/gemma-test && bash start_all.sh gemma4\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
