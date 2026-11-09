"""What the session reads, rendered from the image on every start (`claude-agent-access`): the permission settings, with
the account-writing tools allowed only when `AGENT_ACCOUNT_WRITES=on` — the live account's only when
`AGENT_LIVE_ACCOUNT_WRITES=on`, a switch of its own — and the MCP servers with their token helper.

    python -m claude_agent.render settings <image settings.json> <out>
    python -m claude_agent.render mcp <out>
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

ACCOUNT_WRITES = tuple(
    f"mcp__tc-trading__{tool}"
    for tool in (
        "place_order",
        "close_position",
        "amend_stops",
        "cancel_working_order",
        "switch_active_account",
        "top_up_demo_account",
    )
)

# The live account's writes (`live-account-trading`): no switch and no top-up exist there. Opening the demo account's
# writes never opens these.
LIVE_ACCOUNT_WRITES = tuple(
    f"mcp__tc-trading-live__{tool}"
    for tool in ("place_order", "close_position", "amend_stops", "cancel_working_order")
)

# name, path on the API host, the API its token is for — the same ten as `scripts/claude-mcp.sh`.
SURFACES = (
    ("tc-market", "/market/mcp", "workbench"),
    ("tc-polymarket", "/polymarket/mcp", "workbench"),
    ("tc-social", "/social/mcp", "workbench"),
    ("tc-telegram", "/telegram/mcp", "workbench"),
    ("tc-youtube", "/youtube/mcp", "workbench"),
    ("tc-alerts", "/alerts/mcp", "workbench"),
    ("tc-strategies", "/strategies/mcp", "workbench"),
    ("tc-team-tools", "/team-tools/mcp", "workbench"),
    ("tc-trading", "/trading/mcp", "gateway"),
    ("tc-trading-live", "/trading-live/mcp", "gateway"),
)

HELPER = "/opt/agent/venv/bin/python /opt/agent/bin/mcp_token.py"


def account_writes_on(env: Mapping[str, str]) -> bool:
    """Only the exact word: a typo or an empty value must leave the account closed, never open it."""
    return env.get("AGENT_ACCOUNT_WRITES", "") == "on"


def live_account_writes_on(env: Mapping[str, str]) -> bool:
    return env.get("AGENT_LIVE_ACCOUNT_WRITES", "") == "on"


def settings(image: dict[str, Any], *, writes: bool, live_writes: bool = False) -> dict[str, Any]:
    rendered = json.loads(json.dumps(image))
    permissions = rendered.setdefault("permissions", {})
    every_write = (*ACCOUNT_WRITES, *LIVE_ACCOUNT_WRITES)
    deny = [rule for rule in permissions.get("deny", []) if rule not in every_write]
    allow = [rule for rule in permissions.get("allow", []) if rule not in every_write]
    for switched_on, rules in ((writes, ACCOUNT_WRITES), (live_writes, LIVE_ACCOUNT_WRITES)):
        (allow if switched_on else deny).extend(rules)
    permissions["allow"], permissions["deny"] = allow, deny
    rendered["enabledMcpjsonServers"] = [name for name, _, _ in SURFACES]
    return rendered


def mcp_servers(env: Mapping[str, str]) -> dict[str, Any]:
    host, tenant, client = env["API_HOST"], env["ENTRA_TENANT_ID"], env["AGENT_ENTRA_CLIENT_ID"]
    cache = Path(env.get("CLAUDE_CONFIG_DIR", "/home/agent/.claude")) / "tc-token-cache.bin"
    helper = f"{HELPER} headers --tenant {tenant} --client-id {client} --cache {cache}"
    return {
        "mcpServers": {
            name: {
                "type": "http",
                "url": f"https://{host}{path}",
                "headersHelper": f"{helper} --api {api}",
            }
            for name, path, api in SURFACES
        }
    }


def main(argv: list[str]) -> int:
    match argv:
        case ["settings", source, out]:
            image = json.loads(Path(source).read_text(encoding="utf-8"))
            document = settings(
                image,
                writes=account_writes_on(os.environ),
                live_writes=live_account_writes_on(os.environ),
            )
        case ["mcp", out]:
            document = mcp_servers(os.environ)
        case _:
            print(__doc__, file=sys.stderr)
            return 2
    Path(out).write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
