RunPod Quick Start & Troubleshooting Runbook
===========================================

Purpose: Get a fresh RunPod pod running the gemma-test stack quickly and diagnose common failures (GPU misdetection, port conflicts, missing docs, inference failures).

Prerequisites
- SSH private key with access to the pod (e.g. `~/.ssh/id_ed25519`).
- SSH alias configured (example: `runpod2`) or use `ssh.runpod.io` + pod username.

Common SSH / tunnel command

Run from your workstation (forward ports for UI/API and vLLM):

```bash
ssh -L 8000:localhost:8000 -L 8002:localhost:8002 runpod2
```

If you don't have an alias, use the host and user directly:

```bash
ssh -i ~/.ssh/id_ed25519 <user>@ssh.runpod.io -L 8000:localhost:8000 -L 8002:localhost:8002
```

Quick checklist (first connect)

1. Pull latest code and set up env

```bash
cd /workspace
git clone https://github.com/chafiyounes/gemma-test.git || (cd gemma-test && git fetch origin main && git reset --hard FETCH_HEAD)
cd gemma-test
pip install -r requirements.txt
```

2. Upload SOP documents via SCP:

```bash
scp -r data/documents/ runpod2:/workspace/gemma-test/data/
```

3. Ensure .env points to port 8002 (vLLM)

```bash
sed -i 's|^VLLM_BASE_URL=.*|VLLM_BASE_URL=http://localhost:8002|' .env
```

4. Start vLLM and API

```bash
nohup bash scripts/start_vllm.sh gemma4 > logs/vllm_gemma4.log 2>&1 &
nohup bash scripts/start_api.sh > logs/api.log 2>&1 &
```

Health checks

- vLLM: `curl http://localhost:8002/health`
- API: `curl http://localhost:8000/health`
- Tail logs: `tail -f logs/vllm_*.log logs/api.log`

GPU misdetection (observed problem)

Symptom: Pod shows two GPUs in `nvidia-smi` and PyTorch reports two devices, but CUDA contexts fail on one GPU and vLLM crashes with allocator/caching errors.

Cause: RunPod GPU device indexing can expose a phantom GPU that is inaccessible; processes that try to open CUDA context on that device will OOM or error.

Quick fix (applied in this repo): force vLLM / Python to use a single known-good GPU by setting `CUDA_VISIBLE_DEVICES` before starting the server. Example (already in `scripts/start_vllm.sh`):

```bash
export CUDA_VISIBLE_DEVICES=1
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
bash scripts/start_vllm.sh gemma4
```

If the wrong index is chosen, try `0` or `1` depending on `nvidia-smi` output and which device is healthy.

Root-cause mitigation steps

- Add a pre-start GPU probe that validates device contexts before server start (run `python3 -c 'import torch; torch.cuda.current_device(); print(torch.cuda.get_device_properties(0))'`).
- If a device fails, set `CUDA_VISIBLE_DEVICES` to the other index and restart.

Other frequent issues & remedies

- Port 8001 sidecar conflict: use port 8002 for vLLM (already used in this repo). Ensure tunnel forwards 8002.
- Missing Python packages: run `pip install -r requirements.txt` and `pip install python-docx==1.1.2 bitsandbytes` as needed.
- Missing docs: SCP upload `data/documents/` (ephemeral disk) or implement S3 download in `start_api.sh`.
- Logs inaccessible due to permissions: ensure `mkdir -p logs && chmod 755 logs` before starting services.

Automated diagnostics (local helper)

Run the provided script to collect diagnostics from the pod via SSH:

```bash
python3 scripts/ssh_runpod_diagnostics.py --user <pod-username> --key ~/.ssh/id_ed25519
```

What the script collects

- `nvidia-smi` summary
- PyTorch CUDA device count and device names
- vLLM and API log tails
- bitsandbytes presence
- GPU free memory
- vLLM / API health endpoints
- A quick inference curl against vLLM

Next actions (if errors persist)

1. Collect `dmesg` and `syslog` for GPU driver errors: `dmesg | tail -n 200`.
2. If CUDA driver errors appear, check installed driver version and container CUDA toolkit compatibility.
3. Reboot or request a fresh RunPod pod and re-run `scripts/setup_pod.sh`.

Contact

Add notes here for the on-call or responsible engineer and where to upload collected logs.
