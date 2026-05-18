#!/usr/bin/env bash
# Production build for web_test (chat SPA). Use after git pull on the pod or locally.
set -euo pipefail
PROJ="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJ/web_test"
npm install
npm run build
test -f dist/index.html
