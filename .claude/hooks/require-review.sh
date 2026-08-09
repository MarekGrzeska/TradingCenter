#!/usr/bin/env bash
#
# Refuses to archive a change that has no review.md.
#
# The gate lives here rather than in OpenSpec because OpenSpec does not have one:
# `openspec archive` exits 0 with the review artifact missing, and an `archive.requires`
# block in the schema validates but is ignored. The archive skill only warns and asks.
# A hook is executed by the harness, so it is the one layer a model cannot talk past.
#
# Two ways a change gets archived, and both are covered:
#   openspec archive <name>
#   mv openspec/changes/<name> openspec/changes/archive/<date>-<name>
# The second is the documented happy path — the archive skill uses mkdir + mv, not the
# CLI — so a gate that only watched the CLI would watch the road nobody drives.
#
# **Bash, not PowerShell, because a gate that does not run is not a gate.** The previous
# implementation was `require-review.ps1`, invoked with `"shell": "powershell"`. On a
# machine without `pwsh` on PATH — this project's own macOS one — it could not execute at
# all, so every archive went through unchecked while the settings file said otherwise.
# The cost of the swap is Windows without a bash on PATH; `scripts/dev.ps1` shows that
# platform is used here, so if the gate is ever wanted there, git-bash satisfies this
# script unchanged and is the smaller fix of the two.
#
# Written for bash 3.2 — the version macOS ships. No associative arrays, no `${x,,}`.

set -u

allow() { exit 0; }

deny() {
  # Only backslash and double quote can break the JSON below; the messages are ours and
  # the change name is the sole interpolated value.
  escaped=$(printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g')
  printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s"}}\n' "$escaped"
  exit 0
}

raw=$(cat)
[ -n "$raw" ] || allow

# The fast path, and the reason this hook is cheap enough to sit on every Bash call:
# both detectors below require the literal string `openspec`, so a payload without it
# cannot match either. Bailing here means no JSON parser is spawned for the overwhelming
# majority of commands. This is an exact test, not a heuristic — widen it only alongside
# whatever new detector needs the width.
case $raw in
  *openspec*) ;;
  *) allow ;;
esac

if command -v jq >/dev/null 2>&1; then
  command_line=$(printf '%s' "$raw" | jq -r '.tool_input.command // empty' 2>/dev/null) || allow
elif command -v python3 >/dev/null 2>&1; then
  command_line=$(printf '%s' "$raw" | python3 -c 'import json,sys
try:
    print(json.load(sys.stdin).get("tool_input", {}).get("command", "") or "")
except Exception:
    pass' 2>/dev/null) || allow
else
  # Same posture as the original on unparseable input: this gate exists to stop a
  # mistake, not to hold a door shut, and refusing every command because a parser is
  # missing would be the larger failure.
  allow
fi

[ -n "${command_line:-}" ] || allow

OPENSPEC_RE='(^|[/\])openspec(\.js|\.cmd)?$'
CHANGES_RE="openspec[/\\]+changes[/\\]+([^/\\\"']+)"

lower() { printf '%s' "$1" | tr 'ABCDEFGHIJKLMNOPQRSTUVWXYZ' 'abcdefghijklmnopqrstuvwxyz'; }

# Flags that swallow the next token. Without this, `openspec archive --store trading X`
# reads the store id as the change name and then finds no such change to check.
is_value_flag() {
  case $(lower "$1") in
    --store|--type|--concurrency|--schema|--change) return 0 ;;
  esac
  return 1
}

strip_quotes() {
  s=$1
  while :; do
    case $s in
      \"*|\'*) s=${s#?} ;;
      *) break ;;
    esac
  done
  while :; do
    case $s in
      *\"|*\') s=${s%?} ;;
      *) break ;;
    esac
  done
  printf '%s' "$s"
}

# Both readers work on the global TOKENS array and report their find in TARGET, because
# bash functions return status codes rather than strings.
cli_target() {
  n=${#TOKENS[@]}
  i=0
  # The archive *verb*, not the word anywhere: `openspec instructions archive` is a read
  # and must stay non-blocking.
  while [ $i -lt "$n" ]; do
    [[ ${TOKENS[$i]} =~ $OPENSPEC_RE ]] && break
    i=$((i + 1))
  done
  [ $i -lt "$n" ] || return 1
  i=$((i + 1))

  while [ $i -lt "$n" ]; do
    case ${TOKENS[$i]} in
      -*) is_value_flag "${TOKENS[$i]}" && i=$((i + 1)) ;;
      *) break ;;
    esac
    i=$((i + 1))
  done

  [ $i -lt "$n" ] || return 1
  [ "${TOKENS[$i]}" = "archive" ] || return 1
  i=$((i + 1))

  while [ $i -lt "$n" ]; do
    case ${TOKENS[$i]} in
      -*)
        # `--store trading add-capital-gateway`: without consuming the value, the store
        # id is read as the change name and the check silently targets nothing.
        is_value_flag "${TOKENS[$i]}" && i=$((i + 1))
        i=$((i + 1))
        continue
        ;;
    esac
    TARGET=$(strip_quotes "${TOKENS[$i]}")
    return 0
  done

  # `openspec archive` with no name: the CLI picks interactively, so there is nothing
  # here to check against.
  TARGET=''
  return 0
}

move_target() {
  n=${#TOKENS[@]}
  [ "$n" -ge 2 ] || return 1
  case $(lower "${TOKENS[0]}") in
    mv|move-item|move) ;;
    *) return 1 ;;
  esac

  i=0
  while [ $i -lt "$n" ]; do
    if [[ ${TOKENS[$i]} =~ $CHANGES_RE ]]; then
      candidate=$(strip_quotes "${BASH_REMATCH[1]}")
      # The destination also lives under changes/, so the segment literally named
      # `archive` is skipped and the source is what is left.
      if [ -n "$candidate" ] && [ "$candidate" != "archive" ]; then
        TARGET=$candidate
        return 0
      fi
    fi
    i=$((i + 1))
  done
  return 1
}

TARGET=''
found=0

# Split on shell separators first: a gate that reads the whole line as one command is
# bypassed by putting the archive after a `&&`, and trips over a trailing `;`. Splitting
# on the single characters covers `&&` and `||` too — the extra empty segment is inert.
# The loop reads from a here-document rather than a pipe so that `found` and `TARGET`
# survive it; a pipeline would run it in a subshell and discard both.
while IFS= read -r segment; do
  set -f
  # Deliberately unquoted: this is the word split that turns a segment into tokens.
  # shellcheck disable=SC2206
  TOKENS=($segment)
  set +f
  [ ${#TOKENS[@]} -gt 0 ] || continue

  for token in "${TOKENS[@]}"; do
    case $token in
      --help|-h) continue 2 ;;
    esac
  done

  if cli_target || move_target; then
    found=1
    break
  fi
done <<EOF
$(printf '%s' "$command_line" | tr ';&|\r\n' '\n\n\n\n\n')
EOF

# Nothing here archives anything.
[ "$found" -eq 1 ] || allow

if [ -z "$TARGET" ]; then
  deny 'Name the change explicitly: openspec archive <change-name>. Without a name this hook cannot check that the change has been reviewed.'
fi

# Which checkout the change lives in.
#
# `$CLAUDE_PROJECT_DIR` alone is wrong here, and it took a real archive to notice. It
# names the *primary* worktree, so a change being archived from a secondary one
# (`git worktree add`, which is how parallel work happens in this repo) was looked for in
# a directory the command never touched. That both denies wrongly — the case that caught
# it, a review.md written in one worktree and read for in another — and, worse, could
# allow wrongly, if the primary worktree happened to hold a reviewed change of the same
# name.
#
# So the command's own working directory comes first. The PreToolUse payload carries it;
# older payloads may not, and then the fallbacks stand. From each candidate the search
# walks upward, because `openspec archive` runs just as happily from a module directory
# as from the repository root.
#
# What this still cannot see, and deliberately does not guess at: a command that changes
# directory itself — `cd ../other-worktree && openspec archive x`. The payload reports the
# shell's directory before the command runs, so the gate judges the tree the caller
# started in. Reading the `cd` out of the command string would be guessing at shell
# semantics this hook has no business reimplementing; archive from the checkout you are
# in, which is what the fallback chain assumes.
if command -v jq >/dev/null 2>&1; then
  payload_cwd=$(printf '%s' "$raw" | jq -r '.cwd // empty' 2>/dev/null || true)
fi

find_change_dir() {
  dir=$1
  [ -n "$dir" ] || return 1
  while :; do
    if [ -d "$dir/openspec/changes/$TARGET" ]; then
      printf '%s' "$dir/openspec/changes/$TARGET"
      return 0
    fi
    parent=$(dirname "$dir")
    [ "$parent" != "$dir" ] || return 1
    dir=$parent
  done
}

change_dir=""
for candidate in "${payload_cwd:-}" "${CLAUDE_PROJECT_DIR:-}" "$PWD"; do
  change_dir=$(find_change_dir "$candidate") && break
  change_dir=""
done

# No such change anywhere in reach: let OpenSpec produce its own error rather than
# inventing one here.
[ -n "$change_dir" ] || allow
[ -f "$change_dir/review.md" ] && allow

deny "openspec/changes/$TARGET/review.md is missing. This project reviews a change before archiving it, and the review archives with the change - so it is written first, not skipped. Run: openspec instructions review --change $TARGET --json"
