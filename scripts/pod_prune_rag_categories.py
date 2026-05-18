#!/usr/bin/env python3
"""
On RunPod: remove every direct child under data/documents* except procedures/ and
help_articles/ (matches app_config/settings.py RAG_DEFAULT_CATEGORY +
RAG_EXTRA_CATEGORIES).

Does not run git pull or rebuild. Restarts API so DocStore reloads indexes.
"""
from __future__ import annotations

import importlib.util
import shlex
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

BASH = r"""set -euo pipefail
cd /workspace/gemma-test
for ROOT in data/documents data/documents_md data/documents_txt; do
  [ -d "$ROOT" ] || continue
  while IFS= read -r -d '' path; do
    b=$(basename "$path")
    case "$b" in procedures|help_md|help_articles) continue ;; esac
    echo "Removing: $path"
    rm -rf "$path"
  done < <(find "$ROOT" -mindepth 1 -maxdepth 1 -print0)
done
echo "--- after prune ---"
for ROOT in data/documents data/documents_md data/documents_txt; do
  echo "== $ROOT =="
  ls -la "$ROOT" 2>/dev/null || echo "(missing)"
done
"""


def _load_deploy_runner():
    spec = importlib.util.spec_from_file_location(
        "deploy_runner", REPO_ROOT / "scripts" / "deploy_runner.py"
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    dr = _load_deploy_runner()
    cmd = "bash -lc " + shlex.quote(BASH)
    dr.run_commands(
        [
            cmd,
            "cd /workspace/gemma-test && bash scripts/restart_api.sh",
        ],
        label="pod prune RAG categories + restart api",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
