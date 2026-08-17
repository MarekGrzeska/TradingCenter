"""The save-time checks that need something outside the JSON — `validation.py`.

The shape half (cycles, isolated agents, unknown agent keys on an edge) belongs to
`TeamDefinition` and is tested in `test_contract.py`; what is proven here is that a
refusal over the model catalogue or the tool announcement names the agent it is about,
which is what specs/teams-catalogue requires of every refusal.
"""

from __future__ import annotations

import pytest

from teams.contract import AgentDefinition, TeamDefinition
from teams.tools import AnnouncedSnapshot
from teams.validation import (
    DefinitionRefused,
    check_definition,
    check_trigger_tool,
    check_unattended,
)

MODELS = ("gpt-5.6-luna", "gpt-5.6-mini")


def _agent(key: str, *, model_id: str = "gpt-5.6-luna", tools: list[str] | None = None) -> AgentDefinition:
    return AgentDefinition(
        key=key,
        role=f"the {key}",
        prompt="say something",
        model_id=model_id,
        tools=tools or [],
    )


def snapshot(*names: str, from_: str = "market-mcp", unreachable: list[str] | None = None) -> AnnouncedSnapshot:
    return AnnouncedSnapshot(by_name={name: [from_] for name in names}, unreachable=unreachable or [])


def test_a_definition_naming_known_models_and_announced_tools_passes() -> None:
    definition = TeamDefinition(agents=[_agent("scout", tools=["get_candles"])])
    check_definition(definition, model_ids=MODELS, announced=snapshot("get_candles", "get_symbols"))


def test_a_model_outside_the_catalogue_is_refused_naming_the_agent_and_the_model() -> None:
    definition = TeamDefinition(agents=[_agent("scout"), _agent("judge", model_id="gpt-9-imaginary")])

    with pytest.raises(DefinitionRefused) as err:
        check_definition(definition, model_ids=MODELS, announced=snapshot())

    assert "judge" in str(err.value)
    assert "gpt-9-imaginary" in str(err.value)


def test_a_tool_no_server_announces_is_refused_naming_the_agent_and_the_tool() -> None:
    definition = TeamDefinition(agents=[_agent("scout", tools=["get_candles", "place_order"])])

    with pytest.raises(DefinitionRefused) as err:
        check_definition(definition, model_ids=MODELS, announced=snapshot("get_candles"))

    assert "scout" in str(err.value)
    assert "place_order" in str(err.value)


def test_assigned_tools_with_no_tool_server_are_refused_and_say_so() -> None:
    # Distinct from the case above on purpose: "no server to ask" is a configuration
    # someone can fix, "no server has it" is a definition someone must change.
    definition = TeamDefinition(agents=[_agent("scout", tools=["get_candles"])])

    with pytest.raises(DefinitionRefused) as err:
        check_definition(definition, model_ids=MODELS, announced=None)

    assert "scout" in str(err.value)
    assert "MARKET_MCP_URL" in str(err.value)
    assert "TRADING_MCP_URL" in str(err.value)


def test_a_team_assigning_no_tools_passes_without_a_tool_server() -> None:
    # specs/teams-tool-access: a team whose agents carry no tools never needs a server,
    # at save time or at run time.
    definition = TeamDefinition(agents=[_agent("scout"), _agent("judge")], edges=[])
    check_definition(definition, model_ids=MODELS, announced=None)


def test_a_name_two_servers_announce_is_refused_naming_both() -> None:
    definition = TeamDefinition(agents=[_agent("scout", tools=["place_order"])])
    announced = AnnouncedSnapshot(
        by_name={"place_order": ["market-mcp", "trading-mcp"]}, unreachable=[]
    )

    with pytest.raises(DefinitionRefused) as err:
        check_definition(definition, model_ids=MODELS, announced=announced)

    assert "scout" in str(err.value)
    assert "place_order" in str(err.value)
    assert "market-mcp" in str(err.value)
    assert "trading-mcp" in str(err.value)


def test_a_tool_not_confirmed_because_a_server_was_unreachable_says_so() -> None:
    """Distinct wording from "no server announces it": the tool might be there, this
    module just could not check (specs/teams-tool-access)."""
    definition = TeamDefinition(agents=[_agent("scout", tools=["place_order"])])
    announced = snapshot("get_candles", unreachable=["trading-mcp"])

    with pytest.raises(DefinitionRefused) as err:
        check_definition(definition, model_ids=MODELS, announced=announced)

    assert "scout" in str(err.value)
    assert "place_order" in str(err.value)
    assert "trading-mcp" in str(err.value)
    assert "could not be reached" in str(err.value)


# --- specs/teams-schedules, "Harmonogram nad rewizją z narzędziami zapisującymi wymaga
# jawnego potwierdzenia". `read_only_tools` is the *positive* set — what every configured
# server just announced as read-only — so these tests are also what pins the inversion
# down: the three ways a tool can fail to be confirmed harmless (announced as a write, no
# annotation, nobody answered) all end in the same refusal.


def test_a_revision_carrying_only_confirmed_read_only_tools_needs_no_acknowledgement() -> None:
    definition = TeamDefinition(agents=[_agent("scout", tools=["get_candles"])])
    check_unattended(definition, unattended_ack=False, read_only_tools={"get_candles"})


def test_a_revision_carrying_no_tools_at_all_needs_no_acknowledgement() -> None:
    definition = TeamDefinition(agents=[_agent("scout")])
    check_unattended(definition, unattended_ack=False, read_only_tools=frozenset())


def test_a_revision_naming_a_state_changing_tool_is_refused_without_acknowledgement() -> None:
    definition = TeamDefinition(agents=[_agent("trader", tools=["place_order"])])

    with pytest.raises(DefinitionRefused) as err:
        check_unattended(definition, unattended_ack=False, read_only_tools={"get_candles"})

    assert "trader" in str(err.value)
    assert "place_order" in str(err.value)


def test_a_tool_nobody_could_be_asked_about_is_refused_the_same_way() -> None:
    """The case the inversion exists for: `trading-mcp` down at save time used to make its
    write tools invisible, so the schedule saved without an acknowledgement — and started
    placing orders unattended the moment that server came back."""
    definition = TeamDefinition(agents=[_agent("trader", tools=["place_order"])])

    with pytest.raises(DefinitionRefused) as err:
        check_unattended(definition, unattended_ack=False, read_only_tools=frozenset())

    assert "place_order" in str(err.value)


def test_the_same_revision_is_accepted_with_an_explicit_acknowledgement() -> None:
    definition = TeamDefinition(agents=[_agent("trader", tools=["place_order"])])
    check_unattended(definition, unattended_ack=True, read_only_tools=frozenset())


def test_a_trigger_naming_an_announced_tool_passes() -> None:
    check_trigger_tool("get_candles", announced_tools=["get_candles", "get_symbols"])


def test_a_trigger_naming_a_tool_the_server_does_not_announce_is_refused() -> None:
    with pytest.raises(DefinitionRefused) as err:
        check_trigger_tool("invent_a_price", announced_tools=["get_candles"])

    assert "invent_a_price" in str(err.value)


def test_a_trigger_with_no_tool_server_is_refused_and_says_so() -> None:
    with pytest.raises(DefinitionRefused) as err:
        check_trigger_tool("get_candles", announced_tools=None)

    assert "MARKET_MCP_URL" in str(err.value)
