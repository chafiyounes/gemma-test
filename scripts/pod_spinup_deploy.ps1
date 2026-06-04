# Spin up RunPod + full redeploy (vLLM gemma4 + API + web_test build)
#
# Prerequisites:
#   1. Pod RUNNING in RunPod dashboard (Resume/Start)
#   2. Your SSH public key added in RunPod account settings
#   3. Copy the SSH username from pod Connect tab (changes when pod is recreated)
#
# Usage (PowerShell, from repo root):
#   $env:RUNPOD_SSH_USER = "<user-from-runpod-connect-tab>"
#   .\scripts\pod_spinup_deploy.ps1
#
# Optional — start pod via API first:
#   $env:RUNPOD_API_KEY = "<api-key>"
#   $env:RUNPOD_POD_ID = "<pod-id>"
#   python scripts/runpod_recycle_pod.py --wait-running 180
#   # then set RUNPOD_SSH_USER and run this script again

param(
    [switch]$SkipDeps,
    [ValidateSet("all", "api-only", "none")]
    [string]$Restart = "all"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

if (-not $env:RUNPOD_SSH_USER) {
    Write-Host @"

[!] Set RUNPOD_SSH_USER before deploy (from RunPod -> Connect -> SSH over exposed TCP):
    `$env:RUNPOD_SSH_USER = 'your-pod-user@ssh.runpod.io username part only'
    Example: l8lnmi6ofx0tpz-64411278

"@ -ForegroundColor Yellow
    exit 2
}

Write-Host "[1/3] Testing SSH..." -ForegroundColor Cyan
python scripts/pod_cmd.py --wait 8 "echo CONNECTED && hostname"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "[2/3] Checking chat database on pod..." -ForegroundColor Cyan
python scripts/pod_cmd.py --wait 10 "ls -la /workspace/gemma-test/data/interactions.db 2>/dev/null || echo 'NO interactions.db — chat history may be empty after login'"

$deployArgs = @("scripts/deploy_runner.py")
if ($SkipDeps) { $deployArgs += "--skip-deps" }
$deployArgs += "--restart", $Restart

Write-Host "[3/3] Deploying (restart=$Restart)..." -ForegroundColor Cyan
python @deployArgs
exit $LASTEXITCODE
