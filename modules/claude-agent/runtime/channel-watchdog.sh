#!/usr/bin/env bash
# Claude Code often marks the channel plugin's MCP server "failed" at session start without starting it, while
# `/mcp reconnect` brings it up at once (measured in AgenticEnglish on 2.1.304). Every minute: if the session has a
# channel and its server process is missing, reconnect it.
set -euo pipefail
CHANNELS=${CHANNELS:-}
[ -n "$CHANNELS" ] || exit 0
tmux has-session -t agent 2>/dev/null || exit 0

created=$(tmux display-message -p -t agent '#{session_created}')
[ $(( $(date +%s) - created )) -ge 30 ] || exit 0

# plugin:telegram@claude-plugins-official → MCP server plugin:telegram:telegram, process "bun server.ts"
name=$(echo "$CHANNELS" | sed -E 's/^plugin:([^@]+)@.*/\1/')
pgrep -u "$(id -u)" -f "bun server.ts" >/dev/null && exit 0

echo "[watchdog $(date '+%F %T')] channel $name is down, reconnecting"
tmux send-keys -t agent -l "/mcp reconnect plugin:$name:$name"
tmux send-keys -t agent Enter
