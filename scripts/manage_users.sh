#!/usr/bin/env bash
# Wrapper: run user admin CLI from repo root (loads .env like the API).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
exec python3 scripts/manage_users.py "$@"
