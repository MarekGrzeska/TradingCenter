"""claude-agent-access: the account stays closed unless the deployment says exactly `on`, the tools nobody may call stay
denied either way, and the servers are the ten surfaces with the token for the right API."""

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
    "NotebookEdit",
    "mcp__tc-telegram__send_telegram_message",
)
OUT = "Edit(//home/agent/work/out/**)"
# What the session itself reads: writing there would let a page it fetched widen its own permissions.
WHAT_THE_SESSION_READS = (
    "Edit(//home/agent/work/.claude/**)",
    "Edit(//home/agent/work/CLAUDE.md)",
    "Edit(//home/agent/work/.mcp.json)",
    "Edit(//home/agent/work/owner-channel.md)",
    "Edit(//home/agent/.claude/**)",
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


@pytest.mark.parametrize("writes", [False, True])
def test_the_web_is_open_and_files_are_written_only_to_out(writes: bool) -> None:
    # claude-agent-access, "Artykuł na temat", "Dowolna domena", "Artykuł jako plik HTML"
    permissions = render.settings(IMAGE, writes=writes, live_writes=writes)["permissions"]
    assert {"WebSearch", "WebFetch", OUT} <= set(permissions["allow"])
    assert not {rule for rule in permissions["allow"] if rule.startswith(("Edit", "Write"))} - {OUT}
    assert not {"Edit", "Write", "WebSearch", "WebFetch"} & set(permissions["deny"])
    assert set(WHAT_THE_SESSION_READS) <= set(permissions["deny"])


def test_the_servers_are_the_ten_surfaces_with_their_api() -> None:
    env = {"API_HOST": "api.example", "ENTRA_TENANT_ID": "t", "AGENT_ENTRA_CLIENT_ID": "c"}
    servers = render.mcp_servers(env)["mcpServers"]
    assert len(servers) == 10
    assert servers["tc-trading"]["url"] == "https://api.example/trading/mcp"
    apis = {name: s["headersHelper"].rsplit("--api ", 1)[1] for name, s in servers.items()}
    assert apis.pop("tc-trading") == "gateway"
    assert apis.pop("tc-trading-live") == "gateway"
    assert servers["tc-trading-live"]["url"] == "https://api.example/trading-live/mcp"
    assert set(apis.values()) == {"workbench"}
    assert all("--client-id c" in s["headersHelper"] for s in servers.values())
    assert render.settings(IMAGE, writes=False)["enabledMcpjsonServers"] == list(servers)


def test_the_demo_switch_never_opens_the_live_account() -> None:
    # claude-agent-access, "Zapis na demo włączony, na koncie realnym nie"
    rendered = render.settings(IMAGE, writes=True, live_writes=render.live_account_writes_on({}))
    assert set(render.LIVE_ACCOUNT_WRITES) <= set(rendered["permissions"]["deny"])
    assert set(render.ACCOUNT_WRITES) <= set(rendered["permissions"]["allow"])


@pytest.mark.parametrize("value", ["", "ON", "yes"])
def test_anything_but_on_keeps_the_live_account_closed(value: str) -> None:
    assert not render.live_account_writes_on({"AGENT_LIVE_ACCOUNT_WRITES": value})


def test_on_opens_the_live_account_writes_alone() -> None:
    rendered = render.settings(IMAGE, writes=False, live_writes=True)
    assert set(render.LIVE_ACCOUNT_WRITES) <= set(rendered["permissions"]["allow"])
    assert set(render.ACCOUNT_WRITES) <= set(rendered["permissions"]["deny"])
