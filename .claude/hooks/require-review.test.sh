#!/usr/bin/env bash
#
# Exercises require-review.sh. Run it after touching the hook:
#
#   .claude/hooks/require-review.test.sh
#
# The hook it covers spent its life as PowerShell on a machine with no PowerShell, which
# is a failure nothing reports: a gate that cannot execute allows everything and says
# nothing. That is the case this file exists for — one command that answers whether the
# gate still refuses what it claims to refuse.
#
# Fixtures are a throwaway directory holding two changes: one reviewed, one not.

set -u

here=$(cd "$(dirname "$0")" && pwd)
hook="$here/require-review.sh"

[ -x "$hook" ] || { echo "not executable: $hook" >&2; exit 1; }

fixture=$(mktemp -d)
trap 'rm -rf "$fixture"' EXIT
mkdir -p "$fixture/openspec/changes/with-review" "$fixture/openspec/changes/no-review"
printf '## Verdict\n' > "$fixture/openspec/changes/with-review/review.md"
export CLAUDE_PROJECT_DIR=$fixture

pass=0
fail=0

# <allow|deny> <label> <command>
check() {
  expected=$1
  label=$2
  payload=$(python3 -c 'import json,sys; print(json.dumps({"tool_name":"Bash","tool_input":{"command":sys.argv[1]}}))' "$3")
  output=$(printf '%s' "$payload" | "$hook")
  if printf '%s' "$output" | grep -q '"permissionDecision":"deny"'; then actual=deny; else actual=allow; fi
  if [ "$actual" = "$expected" ]; then
    pass=$((pass + 1))
    printf '  ok    %s\n' "$label"
  else
    fail=$((fail + 1))
    printf '  FAIL  %s — expected %s, got %s\n' "$label" "$expected" "$actual"
    [ -n "$output" ] && printf '        %s\n' "$output"
  fi
}

# <label> <stdin>
check_raw() {
  output=$(printf '%s' "$2" | "$hook")
  if [ -z "$output" ]; then
    pass=$((pass + 1))
    printf '  ok    %s\n' "$1"
  else
    fail=$((fail + 1))
    printf '  FAIL  %s — expected allow, got %s\n' "$1" "$output"
  fi
}

echo "lets through"
check allow "an ordinary command"                  'ls -la modules'
check allow "openspec, but not archiving"          'openspec validate some-change --strict'
check allow "instructions archive is a read"       'openspec instructions archive --json'
check allow "the change has a review"              'openspec archive with-review'
check allow "mv of a reviewed change"              'mv openspec/changes/with-review openspec/changes/archive/2026-08-09-with-review'
check allow "no such change — OpenSpec's error"    'openspec archive no-such-change'
check allow "--help archives nothing"              'openspec archive no-review --help'
check allow "-h archives nothing"                  'openspec archive no-review -h'
check allow "a commit message mentioning archive"  'git commit -m "chore(openspec): archive no-review"'

echo "refuses"
check deny  "archive without a review"             'openspec archive no-review'
check deny  "openspec by absolute path"            '/usr/local/bin/openspec archive no-review'
check deny  "openspec.js through node"             'node ./bin/openspec.js archive no-review'
check deny  "value flag before the verb"           'openspec --store trading archive no-review'
check deny  "value flag after the verb"            'openspec archive --store trading no-review'
check deny  "a quoted change name"                 'openspec archive "no-review"'
check deny  "hidden behind &&"                     'echo start && openspec archive no-review'
check deny  "hidden behind ;"                      'cd /tmp; openspec archive no-review'
check deny  "hidden behind |"                      'true | openspec archive no-review'
check deny  "on a second line"                     'echo a
openspec archive no-review'
check deny  "mv into archive/"                     'mv openspec/changes/no-review openspec/changes/archive/2026-08-09-no-review'
check deny  "mv anywhere else"                     'mv openspec/changes/no-review /tmp/elsewhere'
check deny  "archive with no name at all"          'openspec archive'

echo "edge cases"
check_raw "empty stdin"                            ''
check_raw "input that is not JSON"                 'openspec archive no-review'
check_raw "a payload carrying no command"          '{"tool_name":"BashOutput","tool_input":{"bash_id":"x"}}'

echo
echo "passed: $pass, failed: $fail"
[ "$fail" -eq 0 ]
