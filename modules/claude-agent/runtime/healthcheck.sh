#!/usr/bin/env bash
# Healthy = the tmux session exists and Claude Code runs in it. Not the login, the pairing or the token: those are the
# operator's one-time steps, and a deploy must not be rolled back for a step nobody has taken yet.
set -euo pipefail
tmux has-session -t agent 2>/dev/null
pgrep -u "$(id -u)" -f -- "$(basename "${CLAUDE_BIN:-claude}")" >/dev/null
