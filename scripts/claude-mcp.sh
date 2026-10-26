#!/usr/bin/env bash
# Registers production's tool surfaces in the operator's Claude Code (`operator-mcp-access`), at user scope: available in
# every directory, and never in this repository's `.mcp.json`, where every session working on the code would get them.
#
#   scripts/claude-mcp.sh install <api-host> <tenant-id> <client-id>   # e.g. api.example.com
#   scripts/claude-mcp.sh remove
#
# The client id is `terraform output claude_code_entra_client_id`; sign in once first with
#   uv run --script scripts/mcp_token.py login --tenant <tenant-id> --client-id <client-id>
set -euo pipefail

# name -> path on the API host. YouTube, alerts and strategies answer only where the server mounts them.
SURFACES=(
  "tc-market:/market/mcp"
  "tc-polymarket:/polymarket/mcp"
  "tc-social:/social/mcp"
  "tc-telegram:/telegram/mcp"
  "tc-youtube:/youtube/mcp"
  "tc-alerts:/alerts/mcp"
  "tc-strategies:/strategies/mcp"
  "tc-team-tools:/team-tools/mcp"
  "tc-trading:/trading/mcp"
)

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

remove() {
  for surface in "${SURFACES[@]}"; do
    claude mcp remove --scope user "${surface%%:*}" >/dev/null 2>&1 || true
  done
}

case "${1:-}" in
  install)
    [ $# -eq 4 ] || { echo "usage: $0 install <api-host> <tenant-id> <client-id>" >&2; exit 2; }
    host="$2" tenant="$3" client="$4"
    # Absolute, because Claude Code runs the helper from ~/.claude for a user-scope server, with whatever PATH it has.
    uv_bin="$(command -v uv)" || { echo "uv is not on PATH" >&2; exit 1; }
    helper="$uv_bin run --quiet --script $here/mcp_token.py headers --tenant $tenant --client-id $client"
    remove
    for surface in "${SURFACES[@]}"; do
      name="${surface%%:*}" path="${surface#*:}"
      claude mcp add-json --scope user "$name" \
        "{\"type\":\"http\",\"url\":\"https://$host$path\",\"headersHelper\":\"$helper\"}"
    done
    echo "registered ${#SURFACES[@]} servers; \`claude mcp list\` asks each of them now" >&2
    ;;
  remove)
    remove
    ;;
  *)
    echo "usage: $0 install <api-host> <tenant-id> <client-id> | remove" >&2
    exit 2
    ;;
esac
