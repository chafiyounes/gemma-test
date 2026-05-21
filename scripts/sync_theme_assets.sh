#!/usr/bin/env bash
# Copy shared theme assets to admin_site and web_test public (source of truth: shared/theme/).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$ROOT/shared/theme"
for name in theme-light.css theme-dark.css theme-base.css theme-sync.js; do
  cp "$SRC/$name" "$ROOT/admin_site/assets/$name"
  if [[ "$name" != theme-sync.js ]]; then
    cp "$SRC/$name" "$ROOT/web_test/public/$name"
  fi
done
echo "Theme assets synced from shared/theme/ to admin_site/assets/ and web_test/public/"
