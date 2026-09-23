#!/usr/bin/env bash
# Regenerate (or only check) every committed contract snapshot, and say per file: unchanged, line endings only, changed.
#
#   bash .claude/skills/contract-sync/scripts/sync.sh [--check]
set -uo pipefail

ROOT=$(git rev-parse --show-toplevel)
CHECK_ONLY=$([[ "${1:-}" == "--check" ]] && echo 1 || echo 0)
failed=0

report() {  # one line per generated file under the given paths
  git ls-files -- "$@" | while read -r file; do
    # `M` in `git status` with an empty `git diff` is the CRLF artefact: autocrlf normalises the diff, not the status.
    if [[ -z "$(git status --porcelain -- "$file")" ]]; then
      echo "  unchanged          $file"
    elif git diff --quiet --ignore-cr-at-eol -- "$file"; then
      echo "  line endings only  $file   (nothing to commit; git checkout -- it, or leave it)"
    else
      echo "  CHANGED            $file  ($(git diff --numstat -- "$file" | awk '{print "+"$1" -"$2}'))"
    fi
  done
}

for screen in terminal pocket; do
  echo "== $screen"
  cd "$ROOT/modules/$screen" || exit 1
  if [[ $CHECK_ONLY == 0 ]]; then
    pnpm -s contract:generate >/dev/null 2>&1 || { echo "  generate failed"; failed=1; }
  fi
  pnpm -s contract:check >/dev/null 2>&1 && echo "  contract:check passes" || { echo "  contract:check FAILS"; failed=1; }
  report "src/data/*.generated.ts" 2>/dev/null
done

echo "== trading-mcp (capital-gateway's OpenAPI)"
cd "$ROOT/modules/trading-mcp" || exit 1
if [[ $CHECK_ONLY == 0 ]]; then
  uv run python scripts/contract.py generate >/dev/null 2>&1 || { echo "  generate failed"; failed=1; }
fi
uv run python scripts/contract.py check >/dev/null 2>&1 && echo "  contract.py check passes" || { echo "  contract.py check FAILS"; failed=1; }
report contract/capital-gateway.openapi.json 2>/dev/null

exit $failed
