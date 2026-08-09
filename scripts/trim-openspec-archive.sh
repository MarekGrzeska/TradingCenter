#!/usr/bin/env bash
#
# Keeps an archived OpenSpec change down to what nothing else holds.
#
# A change is archived with five artifacts, and two of them say a second time what is
# already written somewhere better:
#
#   specs/     the delta. Its content was merged into openspec/specs/ at archiving time —
#              that merge is what archiving *is* — so the delta is a copy of the truth,
#              frozen at the moment it stopped being the newest version of it.
#   tasks.md   a checklist with every box ticked. What was done and when is git's job, and
#              git does it better: with the diffs attached.
#
# What stays is what git cannot hand back in readable form:
#
#   proposal.md   why the change was opened
#   design.md     which alternatives were weighed, and why this one
#   review.md     how the result was judged, and against which tests
#   .openspec.yaml
#
# Measured on 10 August 2026, before the first run: 4,010 lines of delta specs and 1,201
# lines of ticked tasks across fourteen changes, growing by roughly 400 a change. The
# archive is not deleted, it is trimmed — and this script is the trimming, so the rule is
# a command rather than something to remember (openspec/config.yaml, archive guidance).
#
# Usage:
#   scripts/trim-openspec-archive.sh            trim, and say what went
#   scripts/trim-openspec-archive.sh --check    say what would go; exit 1 if anything would
#
# Written for bash 3.2, the version macOS ships.

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
