#!/usr/bin/env bash
#
# Keeps an archived OpenSpec change down to what nothing else holds: the delta specs were merged into
# `openspec/specs/` by archiving itself, and a ticked `tasks.md` is what git records better, with the diffs attached.
# What stays is proposal, design and review. Measured before the first run: 5,211 lines across fourteen changes.
#
# Usage:
#   scripts/trim-openspec-archive.sh            trim, and say what went
#   scripts/trim-openspec-archive.sh --check    say what would go; exit 1 if anything would

set -eu

check_only=0
case "${1:-}" in
  --check) check_only=1 ;;
  "") ;;
  *)
    printf 'usage: %s [--check]\n' "$0" >&2
    exit 2
    ;;
esac

root=$(cd "$(dirname "$0")/.." && pwd)
archive="$root/openspec/changes/archive"

if [ ! -d "$archive" ]; then
  echo "no archive at $archive — nothing to trim"
  exit 0
fi

found=0
lines=0

for change in "$archive"/*/; do
  [ -d "$change" ] || continue
  name=$(basename "$change")

  for target in "$change"specs "$change"tasks.md; do
    [ -e "$target" ] || continue
    found=$((found + 1))

    if [ -d "$target" ]; then
      count=$(find "$target" -name '*.md' -exec cat {} + | wc -l | tr -d ' ')
      what="specs/ ($count lines)"
    else
      count=$(wc -l < "$target" | tr -d ' ')
      what="tasks.md ($count lines)"
    fi
    lines=$((lines + count))

    if [ "$check_only" -eq 1 ]; then
      printf '  would remove  %s/%s\n' "$name" "$what"
    else
      rm -rf "$target"
      printf '  removed  %s/%s\n' "$name" "$what"
    fi
  done
done

if [ "$found" -eq 0 ]; then
  echo "archive is already trimmed"
  exit 0
fi

if [ "$check_only" -eq 1 ]; then
  printf '\n%d artifact(s), %d lines, live twice. Run scripts/trim-openspec-archive.sh\n' \
    "$found" "$lines"
  exit 1
fi

printf '\ntrimmed %d artifact(s), %d lines\n' "$found" "$lines"
