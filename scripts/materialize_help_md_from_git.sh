#!/usr/bin/env bash
# Populate data/documents_md/help_md from historical sendit_docs/* in git (never in working tree).
# Safe: only runs when help_md has no *.md yet (or set HELP_MD_BOOTSTRAP_FORCE=1).
set -euo pipefail
cd "$(dirname "$0")/.."
DEST="data/documents_md/help_md"
COMMIT="${HELP_MD_BOOTSTRAP_COMMIT:-8229874}"
mkdir -p "$DEST"
if [[ -n "$(find "$DEST" -maxdepth 1 -name '*.md' -print -quit 2>/dev/null)" ]] && [[ "${HELP_MD_BOOTSTRAP_FORCE:-}" != "1" ]]; then
  echo "help_md already has .md files; set HELP_MD_BOOTSTRAP_FORCE=1 to overwrite."
  exit 0
fi
if ! git cat-file -e "${COMMIT}^{commit}" 2>/dev/null; then
  echo "Commit $COMMIT not in this clone; run full git fetch." >&2
  exit 2
fi
count=0
while IFS= read -r f; do
  [[ -z "$f" ]] && continue
  base=$(basename "$f")
  git show "${COMMIT}:${f}" > "$DEST/$base"
  count=$((count + 1))
done < <(git ls-tree -r --name-only "$COMMIT" -- sendit_docs || true)
echo "materialized ${count} files into $DEST from $COMMIT"
