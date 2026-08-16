"""The half of "can this definition be run" that Pydantic cannot answer.

A definition is refused at the moment it is saved, never at the moment it is run
(specs/teams-catalogue, "Definicja, której nie da się wykonać, jest odrzucana przy
zapisie"). The checks are split by what each one needs to look at, not by taste:

- **shape** — unique agent keys, edges naming real agents, no isolated agent, no cycle —
  lives on `TeamDefinition` itself, because the JSON carries everything those need. A
  body failing them never reaches a route body at all;
- **surroundings** — the model catalogue this module was configured with, and the tools
  the tool server actually announces — lives here, because neither is in the JSON and
  Pydantic has no way to reach either.

Every refusal names the agent it is about. An operator reading "unknown model" against a
team of six roles has been told nothing (specs/teams-catalogue, "Odmowa MUST nazywać
agenta albo zależność, przez którą zapadła").
"""

from __future__ import annotations

from collections.abc import Collection

from .contract import TeamDefinition
from .tools import AnnouncedSnapshot


class DefinitionRefused(ValueError):
    """The definition parses and its graph is sound, but this module cannot run it."""


def check_definition(
    definition: TeamDefinition,
    *,
    model_ids: Collection[str],
    announced: AnnouncedSnapshot | None,
) -> None:
    """Raises `DefinitionRefused` naming the agent at fault, or returns.

    `announced` is `None` when this module has no tool server configured at all. That is
    not the same as "no server announces this tool", and the refusal below says which of
    the two it is — and, when it is neither, whether the name simply is not announced or
    is announced by more than one server. Note the asymmetry with a *run*: a run of a
    team whose agents carry no tools proceeds with no tool server at all (specs/
    teams-tool-access), and so does a save of one — only an agent actually assigned a
    tool needs the announcement to check it against.
    """
    _every_agent_names_a_known_model(definition, model_ids)
    _every_assigned_tool_is_announced(definition, announced)


def check_runnable(definition: TeamDefinition, *, model_ids: Collection[str]) -> None:
    """The same model check, at the moment a saved revision is about to run.

    Not redundant with `check_definition`: a revision saved a month ago names whatever
    the catalogue held then, and a model dropped from the configuration since is exactly
    the case specs/teams-models cares about — the revision and every run it already has
    stay readable, and only *starting a new one* is refused, naming the agent and the
    model (there is no substitution, silent or otherwise).

    The tool half of this check belongs here too and arrives with the tool session in
    group 6 — a revision naming a tool the server no longer announces is the same shape
    of refusal (specs/teams-tool-access, "Narzędzie znika po stronie serwera").
    """
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
    definition: TeamDefinition, announced: AnnouncedSnapshot | None
) -> None:
    assigning = [agent for agent in definition.agents if agent.tools]
    if not assigning:
        return

    if announced is None:
        agent = assigning[0]
        raise DefinitionRefused(
            f"agent {agent.key!r} is assigned tool(s) {sorted(agent.tools)}, but this "
            "module has no tool server configured to check them against — set "
            "MARKET_MCP_URL and/or TRADING_MCP_URL, or save the team with no tools "
            "assigned"
        )

    for agent in assigning:
        collided = sorted(
            tool for tool in agent.tools if len(announced.by_name.get(tool, [])) > 1
        )
        if collided:
            tool = collided[0]
            servers = " and ".join(announced.by_name[tool])
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
        raise DefinitionRefused(
            f"agent {agent.key!r} is assigned tool(s) {unknown}, which no configured "
            f"tool server announces ({sorted(known)})"
        )
