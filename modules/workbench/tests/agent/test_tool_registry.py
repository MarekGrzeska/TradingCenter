"""Several sources of tools behind one door — specs/agent-tool-access.

The property under test is independence: one source being absent, unreachable or slow costs
the model that source's tools and nothing else. It is easy to write a registry that loses
this by gathering everything and failing as a unit, and the failure is invisible until the
day one of them is down.

Two of the three are servers on a network; the third runs in this process and is handed in
rather than built from settings, because building one needs the application object
(`workbench/team_tools.py`). The stand-in below is all three — what the registry knows about
a source is five members, and it does not ask which kind it is.
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

    def __init__(
        self,
        label: str,
        tools: list[str],
        *,
        configured: bool = True,
        account_tools: frozenset[str] = frozenset(),
    ) -> None:
        self.label = label
        self.configured = configured
        self._tools = tools
        self._account_tools = account_tools
        self.calls: list[tuple[str, str | None]] = []
        self.closed = False

    async def list_tools(self, operator_principal: str | None = None) -> list[ToolDescriptor]:
        return [ToolDescriptor(name=name, description="", input_schema={}) for name in self._tools]

    def moves_the_account(self, name: str) -> bool:
        return name in self._account_tools

    async def call(self, name, arguments, operator_principal=None) -> ToolOutcome:
        self.calls.append((name, operator_principal))
        return ToolOutcome(ToolOutcomeKind.OK, f"{self.label} ran {name}", 1)

    async def aclose(self) -> None:
        self.closed = True


class _UnreachableServer(_Server):
    async def list_tools(self, operator_principal: str | None = None) -> list[ToolDescriptor]:
        # What `ToolServer` really does when it cannot be asked: an empty list, never an
        # exception (specs/agent-tool-access, "Brak serwera narzędzi nie odbiera agentowi
        # mowy").
        return []


def test_from_settings_builds_the_two_servers_that_are_on_a_network() -> None:
    registry = ToolServerRegistry.from_settings(_settings())
    # Reaching inside on purpose: which sources get built is the arrangement this test
    # pins. The team tools are not among them and cannot be — settings hold no address for
    # something in this process.
    assert [server.label for server in registry._servers] == ["market-mcp", "trading-mcp"]


def test_a_local_source_is_appended_to_the_servers_rather_than_replacing_one() -> None:
    team_tools = _Server("team tools", ["create_team"])

    registry = ToolServerRegistry.from_settings(_settings(), local_sources=[team_tools])

    labels = [server.label for server in registry._servers]
    assert labels == ["market-mcp", "trading-mcp", "team tools"]


async def test_the_local_source_answers_while_neither_server_is_configured() -> None:
    """The asymmetry worth pinning: a network server with no address publishes nothing, and
    a source in this process has no address to lack."""
    registry = ToolServerRegistry.from_settings(
        _settings(), local_sources=[_Server("team tools", ["create_team"])]
    )

    names = [tool.name for tool in await registry.list_tools()]

    assert names == ["create_team"]


def test_only_trading_mcp_is_built_as_a_server_that_can_move_the_account() -> None:
    registry = ToolServerRegistry.from_settings(_settings())

    moving = {
        server.label for server in registry._servers if server.can_move_the_account
    }

    assert moving == {"trading-mcp"}


async def test_whether_a_name_moves_the_account_is_answered_by_its_own_server() -> None:
    # specs/agent-trading, "Wywołanie ruszające rachunek zostawia ślad przed wysłaniem" —
    # the registry has to route this question the same way it routes the call itself.
    market = _Server("market-mcp", ["get_candles"])
    trading = _Server(
        "trading-mcp", ["get_positions", "place_order"], account_tools=frozenset({"place_order"})
    )
    registry = ToolServerRegistry([market, trading])
    await registry.list_tools()

    assert registry.moves_the_account("place_order") is True
    assert registry.moves_the_account("get_positions") is False
    assert registry.moves_the_account("get_candles") is False


async def test_a_name_nobody_announced_does_not_move_the_account() -> None:
    # `call` refuses it without sending anything, so there is nothing to trace.
    registry = ToolServerRegistry([_Server("trading-mcp", [], account_tools=frozenset({"x"}))])
    await registry.list_tools()

    assert registry.moves_the_account("place_order") is False


def test_nothing_configured_means_no_tools_rather_than_an_error() -> None:
    registry = ToolServerRegistry([_Server("market-mcp", [], configured=False)])
    assert registry.configured is False


async def test_the_union_of_both_catalogues_reaches_the_model() -> None:
    registry = ToolServerRegistry(
        [_Server("market-mcp", ["get_candles"]), _Server("team tools", ["create_team"])]
    )

    names = [tool.name for tool in await registry.list_tools()]

    assert names == ["get_candles", "create_team"]


async def test_one_server_being_unreachable_leaves_the_others_tools_in_place() -> None:
    market = _UnreachableServer("market-mcp", ["get_candles"])
    teams = _Server("team tools", ["create_team"])
    registry = ToolServerRegistry([market, teams])

    names = [tool.name for tool in await registry.list_tools()]

    assert names == ["create_team"]


async def test_a_call_reaches_the_source_that_announced_the_name() -> None:
    market = _Server("market-mcp", ["get_candles"])
    teams = _Server("team tools", ["create_team"])
    registry = ToolServerRegistry([market, teams])
    await registry.list_tools()

    await registry.call("create_team", {}, "operator-principal")

    assert teams.calls == [("create_team", "operator-principal")]
    assert market.calls == []


async def test_the_operators_identity_travels_to_every_source_the_registry_dispatches_to() -> None:
    """The registry does not decide who needs it — the source does, and the one that does
    not want it never looks at it. Keeping the decision in one place is what stops a further
    source from being added without one."""
    market = _Server("market-mcp", ["get_candles"])
    registry = ToolServerRegistry([market])
    await registry.list_tools()

    await registry.call("get_candles", {}, "operator-principal")

    assert market.calls == [("get_candles", "operator-principal")]


async def test_a_name_nobody_announces_is_an_outcome_not_an_exception() -> None:
    registry = ToolServerRegistry([_Server("market-mcp", ["get_candles"])])
    await registry.list_tools()

    outcome = await registry.call("create_team", {})

    assert outcome.kind is ToolOutcomeKind.UNAVAILABLE
    assert "create_team" in outcome.text


async def test_a_name_two_servers_both_announce_is_offered_by_neither() -> None:
    """Guessing would send an operator's "run it" to whichever server sorted first."""
    registry = ToolServerRegistry(
        [_Server("market-mcp", ["run_team"]), _Server("team tools", ["run_team"])]
    )

    names = [tool.name for tool in await registry.list_tools()]

    assert names == ["run_team"]  # the first announcement stands; the second is dropped
    outcome = await registry.call("run_team", {})
    assert outcome.kind is ToolOutcomeKind.OK


async def test_closing_the_registry_closes_every_server() -> None:
    market, teams = _Server("market-mcp", []), _Server("team tools", [])
    await ToolServerRegistry([market, teams]).aclose()

    assert market.closed and teams.closed


@pytest.mark.parametrize(
    ("prefix", "url", "scope", "expected"),
    [
        ("MARKET_MCP", "https://market.example.com", None, "MARKET_MCP_SCOPE"),
        ("MARKET_MCP", "http://127.0.0.1:8020", "api://market/.default", "loopback"),
        ("TRADING_MCP", "https://trading.example.com", None, "TRADING_MCP_SCOPE"),
        ("TRADING_MCP", "http://127.0.0.1:8060", "api://trading/.default", "loopback"),
        ("TRADING_MCP", None, "api://trading/.default", "TRADING_MCP_URL"),
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
    settings = _settings(market_mcp_url="http://127.0.0.1:8020")

    assert settings.market_mcp_url == "http://127.0.0.1:8020"
    assert settings.trading_mcp_url is None


def test_the_trading_server_is_configured_without_touching_the_other() -> None:
    settings = _settings(trading_mcp_url="http://127.0.0.1:8060/")

    # The trailing slash goes, the same as market-mcp's, so nothing downstream builds `//mcp`.
    assert settings.trading_mcp_url == "http://127.0.0.1:8060"
    assert settings.market_mcp_url is None


def test_the_trading_servers_ceiling_matches_what_trading_mcp_waits_for() -> None:
    """trading-mcp waits on the gateway for up to 30s. A lower ceiling here would time out
    this side of an order that had already been sent (design.md, D4)."""
    assert _settings().trading_mcp_request_timeout_seconds >= 30.0
