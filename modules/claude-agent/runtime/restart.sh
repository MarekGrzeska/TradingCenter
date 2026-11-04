#!/usr/bin/env bash
# Nightly restart: the next session starts with a clean context. The entrypoint's loop brings it back.
set -euo pipefail
STATE=${AGENT_STATE_DIR:-${CLAUDE_CONFIG_DIR:-$HOME/.claude}/agent-state}
mkdir -p "$STATE"
touch "$STATE/fresh-next"
tmux kill-session -t agent 2>/dev/null || true
echo "[restart $(date '+%F %T')] session stopped; next start is fresh"
