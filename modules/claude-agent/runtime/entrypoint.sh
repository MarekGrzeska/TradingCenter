#!/usr/bin/env bash
# The agent container's main process (under tini), after AgenticEnglish's infra/runtime/entrypoint.sh. Refuses to run
# with an API key, renders the session's instructions, settings and MCP servers from the image, starts the scheduler,
# and keeps exactly one Claude Code session alive in tmux.
set -euo pipefail

SRC=${AGENT_SRC:-/opt/agent/agent}
WORKDIR=${AGENT_WORKDIR:-/home/agent/work}
CONFIG=${CLAUDE_CONFIG_DIR:-$HOME/.claude}
STATE=${AGENT_STATE_DIR:-$CONFIG/agent-state}
PY=${AGENT_PYTHON:-/opt/agent/venv/bin/python}
CLAUDE_BIN=${CLAUDE_BIN:-claude}
CHANNELS=${CHANNELS:-}
SESSION=agent

log() { echo "[entrypoint $(date '+%F %T')] $*"; }
die() { echo "[entrypoint] REFUSING TO START: $*" >&2; exit 64; }

# 1. Zero API. It must say exactly "zero-api: ok": a check that did not run is a refusal too.
zero_api=$("$PY" -m claude_agent.zero_api "$CONFIG/settings.json" "$SRC/.claude/settings.json" \
  "$WORKDIR/.claude/settings.local.json") || die "see the line above"
[ "$zero_api" = "zero-api: ok" ] || die "the zero-API check did not run (said: ${zero_api:-nothing})"

# 2. Instructions, skills, settings and servers come from the image on every start; edits in the workdir are gone.
mkdir -p "$WORKDIR" "$CONFIG" "$STATE"
rm -rf "$WORKDIR/.claude" "$WORKDIR/CLAUDE.md" "$WORKDIR/.mcp.json"
cp -r "$SRC/CLAUDE.md" "$SRC/.claude" "$WORKDIR/"
"$PY" -m claude_agent.render settings "$SRC/.claude/settings.json" "$WORKDIR/.claude/settings.json"
"$PY" -m claude_agent.render mcp "$WORKDIR/.mcp.json"
# What the agent writes for the operator (an article as HTML, sent on Telegram) lives a week.
mkdir -p "$WORKDIR/out"
find "$WORKDIR/out" -type f -mtime +7 -delete
[ "${AGENT_ACCOUNT_WRITES:-}" = on ] && log "account writes: ON (demo)" || log "account writes: off"
[ "${AGENT_LIVE_ACCOUNT_WRITES:-}" = on ] && log "LIVE account writes: ON (real money)" || log "live account writes: off"

# New instructions (a deploy) start a fresh conversation rather than continue one held under the old ones.
instructions=$(cd "$WORKDIR" && find CLAUDE.md .mcp.json .claude -type f -print0 | sort -z | xargs -0 sha256sum | sha256sum | cut -d' ' -f1)
if [ "$(cat "$STATE/instructions" 2>/dev/null)" != "$instructions" ]; then
  log "instructions changed: the next session starts fresh"
  touch "$STATE/fresh-next"
  echo "$instructions" >"$STATE/instructions"
fi

# The plugin keeps its bot token next to its inbox, so these stay private, as the plugin itself would create them.
mkdir -p -m 700 "$CONFIG/channels" && mkdir -p -m 700 "$CONFIG/channels/telegram"

if [ -n "${AGENT_TELEGRAM_OWNER_CHAT_ID:-}" ]; then
  printf '# Operator channel\n\nTelegram chat_id: %s\n' "$AGENT_TELEGRAM_OWNER_CHAT_ID" >"$WORKDIR/owner-channel.md"
else
  log "AGENT_TELEGRAM_OWNER_CHAT_ID is not set: check-ins are printed in the session, not sent"
fi

# 3. Trust the workdir and approve its servers, or a dialog in the headless tmux waits forever; Remote Control with
#    every session, so the Claude app reaches it after a restart too.
cfg="$CONFIG/.claude.json"
[ -s "$cfg" ] || echo '{}' >"$cfg"
servers=$(jq -c '.mcpServers | keys' "$WORKDIR/.mcp.json")
tmp=$(mktemp)
jq --arg p "$WORKDIR" --argjson s "$servers" '.projects[$p].hasTrustDialogAccepted = true
  | .projects[$p].enabledMcpjsonServers = $s
  | .remoteControlAtStartup = true' "$cfg" >"$tmp" && cat "$tmp" >"$cfg" && rm -f "$tmp"

# 4. Scheduler.
"$PY" -m claude_agent.checkin crontab >"$STATE/crontab"
log "crontab:"; sed 's/^/    /' "$STATE/crontab"
supercronic "$STATE/crontab" &

# 5. One session, forever. A crash continues the last conversation; a requested restart starts clean. Claude Code
#    connects its MCP servers once, at session start, and does not retry: wait (at most 2 minutes) for the workbench.
transcripts="$CONFIG/projects/$(echo "$WORKDIR" | sed 's/[^A-Za-z0-9]/-/g')"
wait_for_workbench() {
  [ -n "${API_HOST:-}" ] || return 0
  for _ in $(seq 1 60); do
    curl -fsS --max-time 2 "https://$API_HOST/health" >/dev/null 2>&1 && return 0
    sleep 2
  done
  log "https://$API_HOST/health did not answer; starting without waiting longer"
}
while true; do
  wait_for_workbench
  args=()
  [ -z "$CHANNELS" ] || args+=(--channels "$CHANNELS")
  if [ -f "$STATE/fresh-next" ]; then
    rm -f "$STATE/fresh-next"
    mode=fresh
  elif compgen -G "$transcripts/*.jsonl" >/dev/null; then
    args+=(--continue)
    mode=continue
  else
    mode=fresh
  fi
  cmd=$(printf '%q ' "$CLAUDE_BIN" "${args[@]}")
  log "starting session ($mode): $cmd"
  tmux new-session -d -s "$SESSION" -x 200 -y 50 -c "$WORKDIR" "$cmd"
  while tmux has-session -t "$SESSION" 2>/dev/null; do sleep 5; done
  log "session ended"
  sleep 5
done
