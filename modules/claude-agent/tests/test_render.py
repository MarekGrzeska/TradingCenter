"""claude-agent-access: the account stays closed unless the deployment says exactly `on`, the tools nobody may call stay
denied either way, and the servers are the nine surfaces with the token for the right API."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from claude_agent import render

IMAGE = json.loads(
    (Path(__file__).parents[1] / "agent" / ".claude" / "settings.json").read_text("utf-8")
)
NEVER = (
    "Bash",
    "Edit",
    "Write",
    "WebFetch",
    "WebSearch",
    "mcp__tc-telegram__send_telegram_message",
)


@pytest.mark.parametrize("value", ["", "ON", "yes", "true", "on "])
def test_anything_but_on_keeps_account_writes_denied(value: str) -> None:
    writes = render.account_writes_on({"AGENT_ACCOUNT_WRITES": value})
    rendered = render.settings(IMAGE, writes=writes)
    assert set(render.ACCOUNT_WRITES) <= set(rendered["permissions"]["deny"])
    assert not set(render.ACCOUNT_WRITES) & set(rendered["permissions"]["allow"])


def test_on_moves_the_account_writes_from_deny_to_allow() -> None:
    writes = render.account_writes_on({"AGENT_ACCOUNT_WRITES": "on"})
    rendered = render.settings(IMAGE, writes=writes)
    assert set(render.ACCOUNT_WRITES) <= set(rendered["permissions"]["allow"])
    assert not set(render.ACCOUNT_WRITES) & set(rendered["permissions"]["deny"])


@pytest.mark.parametrize("writes", [False, True])
def test_what_nobody_may_call_stays_denied(writes: bool) -> None:
    rendered = render.settings(IMAGE, writes=writes)
    assert set(NEVER) <= set(rendered["permissions"]["deny"])
    assert rendered["permissions"]["defaultMode"] == "dontAsk"


def test_the_servers_are_the_nine_surfaces_with_their_api() -> None:
    env = {"API_HOST": "api.example", "ENTRA_TENANT_ID": "t", "AGENT_ENTRA_CLIENT_ID": "c"}
    servers = render.mcp_servers(env)["mcpServers"]
    assert len(servers) == 9
    assert servers["tc-trading"]["url"] == "https://api.example/trading/mcp"
    apis = {name: s["headersHelper"].rsplit("--api ", 1)[1] for name, s in servers.items()}
    assert apis.pop("tc-trading") == "gateway"
    assert set(apis.values()) == {"workbench"}
    assert all("--client-id c" in s["headersHelper"] for s in servers.values())
    assert render.settings(IMAGE, writes=False)["enabledMcpjsonServers"] == list(servers)
