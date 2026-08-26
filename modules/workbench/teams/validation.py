"""The half of "can this definition be run" that Pydantic cannot answer: shape lives on `TeamDefinition`, surroundings
live here. Every refusal names its agent — "unknown model" against a team of six roles has told the operator nothing."""

from __future__ import annotations

from collections.abc import Collection

from .contract import TeamDefinition
from .tools import AnnouncedSnapshot, and_list


class DefinitionRefused(ValueError):
    """The definition parses and its graph is sound, but this module cannot run it."""


def check_definition(
    definition: TeamDefinition,
    *,
    model_ids: Collection[str],
    announced: AnnouncedSnapshot,
) -> None:
    """Raises `DefinitionRefused` naming the agent at fault, or returns. Note the asymmetry with a run: a team whose
    agents carry no tools saves and runs with no server at all, and only an assigned tool needs an announcement."""
    _every_agent_names_a_known_model(definition, model_ids)
    _every_assigned_tool_is_announced(definition, announced)


def check_runnable(definition: TeamDefinition, *, model_ids: Collection[str]) -> None:
    """The same model check, at the moment a saved revision is about to run. Not redundant: a revision saved
    a month ago names whatever the catalogue held then, and only starting a new run is refused."""
    _every_agent_names_a_known_model(definition, model_ids)


def _every_agent_names_a_known_model(
    definition: TeamDefinition, model_ids: Collection[str]
) -> None:
    known = set(model_ids)
    for agent in definition.agents:
        if agent.model_id not in known:
            raise DefinitionRefused(
                f"agent {agent.key!r} names model {agent.model_id!r}, which is not in this "
                f"module's model catalogue ({sorted(known)})"
            )


def _every_assigned_tool_is_announced(
    definition: TeamDefinition, announced: AnnouncedSnapshot
) -> None:
    assigning = [agent for agent in definition.agents if agent.tools]
    if not assigning:
        return

    for agent in assigning:
        collided = sorted(
            tool for tool in agent.tools if len(announced.by_name.get(tool, [])) > 1
        )
        if collided:
            tool = collided[0]
            # Every server announcing it, not the first two: a message that stops short sends the operator
            # to unconfigure one and meet this same refusal again.
            servers = and_list(announced.by_name[tool])
            raise DefinitionRefused(
                f"agent {agent.key!r} is assigned tool {tool!r}, which more than one "
                f"tool server announces ({servers}) — this module cannot tell which "
                "was meant"
            )

    known = set(announced.by_name)
    for agent in assigning:
        unknown = sorted(tool for tool in agent.tools if tool not in known)
        if not unknown:
            continue
        if announced.unreachable:
            raise DefinitionRefused(
                f"agent {agent.key!r} is assigned tool(s) {unknown}, but "
                f"{' and '.join(announced.unreachable)} could not be reached to "
                "confirm them"
            )
        if announced.unconfigured:
            # A server with no address at all, worth keeping apart from "answered and does not have it":
            # the operator's next move is a setting rather than a different tool.
            raise DefinitionRefused(
                f"agent {agent.key!r} is assigned tool(s) {unknown}, and "
                f"{' and '.join(announced.unconfigured)} "
                f"{'has' if len(announced.unconfigured) == 1 else 'have'} no address "
                f"configured to check them against — set {_url_settings(announced)}, "
                "or assign only tools this module announces "
                f"({sorted(known)})"
            )
        # Phase 2's wording: there can be two servers now, so the refusal says "no
        # configured tool server" rather than naming the one there used to be.
        raise DefinitionRefused(
            f"agent {agent.key!r} is assigned tool(s) {unknown}, which no configured "
            f"tool server announces ({sorted(known)})"
        )


def _url_settings(announced: AnnouncedSnapshot) -> str:
    """The settings the operator has to fill, derived from the labels rather than listed. A hand-kept list
    here named two servers on the day there were three, and it would have gone on naming two."""
    return " and/or ".join(
        f"{label.replace('-', '_').upper()}_URL" for label in announced.unconfigured
    )


def check_trigger_tool(tool_name: str, *, announced_tools: Collection[str] | None) -> None:
    """The same shape of check `_every_assigned_tool_is_announced` runs for a team's own agents, run instead
    for the one tool a trigger's condition calls."""
    if announced_tools is None:
        raise DefinitionRefused(
            f"trigger names tool {tool_name!r}, but this module has no tool server to "
            "check it against — configure MARKET_MCP_URL, or do not save this trigger"
        )
    known = set(announced_tools)
    if tool_name not in known:
        raise DefinitionRefused(
            f"trigger names tool {tool_name!r}, which the tool server does not announce "
            f"({sorted(known)})"
        )
