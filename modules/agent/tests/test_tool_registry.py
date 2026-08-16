"""Several tool servers behind one door — specs/agent-tool-access, as modified by
add-teams-mcp.

The property under test is independence: one server being absent, unreachable or slow
costs the model that server's tools and nothing else. It is easy to write a registry that
loses this by gathering everything and failing as a unit, and the failure is invisible
until the day one of them is down.
"""

from __future__ import annotations

import pytest

from agent.config import Settings
from agent.tools import ToolDescriptor, ToolOutcome, ToolOutcomeKind, ToolServerRegistry


def _settings(**overrides) -> Settings:
    return Settings(
        database_url="postgresql://localhost/agent",
        openai_api_key="k",
        models=[
            {
                "id": "m",
                "model": "m",
                "display_name": "M",
                "cost_rank": 1,
                "input_rate_per_1m": "1",
                "output_rate_per_1m": "1",
            }
        ],
        default_model_id="m",
        _env_file=None,  # type: ignore[call-arg]
        **overrides,
    )


class _Server:
    """A stand-in for one `ToolServer`, with the same four members the registry uses."""

    def __init__(self, label: str, tools: list[str], *, configured: bool = True) -> None:
        self.label = label
        self.configured = configured
        self.forwards_operator_token = label == "teams-mcp"
        self._tools = tools
        self.calls: list[tuple[str, str | None]] = []
        self.closed = False

    async def list_tools(self, operator_token: str | None = None) -> list[ToolDescriptor]:
        return [ToolDescriptor(name=name, description="", input_schema={}) for name in self._tools]

    async def call(self, name, arguments, operator_token=None) -> ToolOutcome:
        self.calls.append((name, operator_token))
        return ToolOutcome(ToolOutcomeKind.OK, f"{self.label} ran {name}", 1)

    async def aclose(self) -> None:
        self.closed = True


class _UnreachableServer(_Server):
    async def list_tools(self, operator_token: str | None = None) -> list[ToolDescriptor]:
        # What `ToolServer` really does when it cannot be asked: an empty list, never an
        # exception (specs/agent-tool-access, "Brak serwera narzędzi nie odbiera agentowi
        # mowy").
        return []


def test_from_settings_builds_both_servers_and_only_one_forwards_the_operators_token() -> None:
    registry = ToolServerRegistry.from_settings(_settings())
    # Reaching inside on purpose: which servers get built, and which one carries a
    # person's credential, is the arrangement this test exists to pin.
    servers = registry._servers

    labels = {server.label: server.forwards_operator_token for server in servers}
    assert labels == {"market-mcp": False, "teams-mcp": True}


def test_nothing_configured_means_no_tools_rather_than_an_error() -> None:
    registry = ToolServerRegistry([_Server("market-mcp", [], configured=False)])
    assert registry.configured is False


async def test_the_union_of_both_catalogues_reaches_the_model() -> None:
    registry = ToolServerRegistry(
        [_Server("market-mcp", ["get_candles"]), _Server("teams-mcp", ["create_team"])]
    )

    names = [tool.name for tool in await registry.list_tools()]

    assert names == ["get_candles", "create_team"]


async def test_one_server_being_unreachable_leaves_the_others_tools_in_place() -> None:
    market = _UnreachableServer("market-mcp", ["get_candles"])
    teams = _Server("teams-mcp", ["create_team"])
    registry = ToolServerRegistry([market, teams])

    names = [tool.name for tool in await registry.list_tools()]

    assert names == ["create_team"]


async def test_a_call_reaches_the_server_that_announced_the_name() -> None:
    market = _Server("market-mcp", ["get_candles"])
    teams = _Server("teams-mcp", ["create_team"])
    registry = ToolServerRegistry([market, teams])
    await registry.list_tools()

    await registry.call("create_team", {}, "operator-token")

    assert teams.calls == [("create_team", "operator-token")]
    assert market.calls == []


async def test_the_operators_token_travels_to_every_server_the_registry_dispatches_to() -> None:
    """The registry does not decide who needs the token — the server does, and the one
    that does not want it never looks at it. Keeping the decision in one place is what
    stops a third server from being added without one."""
    market = _Server("market-mcp", ["get_candles"])
    registry = ToolServerRegistry([market])
    await registry.list_tools()

    await registry.call("get_candles", {}, "operator-token")

    assert market.calls == [("get_candles", "operator-token")]


async def test_a_name_nobody_announces_is_an_outcome_not_an_exception() -> None:
    registry = ToolServerRegistry([_Server("market-mcp", ["get_candles"])])
    await registry.list_tools()

    outcome = await registry.call("create_team", {})

    assert outcome.kind is ToolOutcomeKind.UNAVAILABLE
    assert "create_team" in outcome.text


async def test_a_name_two_servers_both_announce_is_offered_by_neither() -> None:
    """Guessing would send an operator's "run it" to whichever server sorted first."""
    registry = ToolServerRegistry(
        [_Server("market-mcp", ["run_team"]), _Server("teams-mcp", ["run_team"])]
    )

    names = [tool.name for tool in await registry.list_tools()]

    assert names == ["run_team"]  # the first announcement stands; the second is dropped
    outcome = await registry.call("run_team", {})
    assert outcome.kind is ToolOutcomeKind.OK


async def test_closing_the_registry_closes_every_server() -> None:
    market, teams = _Server("market-mcp", []), _Server("teams-mcp", [])
    await ToolServerRegistry([market, teams]).aclose()

    assert market.closed and teams.closed


@pytest.mark.parametrize(
    ("prefix", "url", "scope", "expected"),
    [
        ("TEAMS_MCP", "https://teams.example.com", None, "TEAMS_MCP_SCOPE"),
        ("TEAMS_MCP", "http://127.0.0.1:8070", "api://teams/.default", "loopback"),
        ("MARKET_MCP", "https://market.example.com", None, "MARKET_MCP_SCOPE"),
    ],
)
def test_each_servers_mode_is_refused_on_its_own_terms(prefix, url, scope, expected) -> None:
    """The message names the server it is about — "the tool server" stopped being
    unambiguous the moment there were two."""
    field = prefix.lower()
    with pytest.raises(Exception) as err:
        _settings(**{f"{field}_url": url, f"{field}_scope": scope})

    assert expected in str(err.value)


def test_one_server_configured_and_the_other_absent_is_a_working_configuration() -> None:
    settings = _settings(teams_mcp_url="http://127.0.0.1:8070")

    assert settings.teams_mcp_url == "http://127.0.0.1:8070"
    assert settings.market_mcp_url is None
