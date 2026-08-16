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


class DefinitionRefused(ValueError):
    """The definition parses and its graph is sound, but this module cannot run it."""


def check_definition(
    definition: TeamDefinition,
    *,
    model_ids: Collection[str],
    announced_tools: Collection[str] | None,
) -> None:
    """Raises `DefinitionRefused` naming the agent at fault, or returns.

    `announced_tools` is `None` when this module has no session with a tool server — it
    was configured without one, or the session is not up. That is not the same as "the
    server announces nothing", and the refusal below says which of the two it is. Note
    the asymmetry with a *run*: a run of a team whose agents carry no tools proceeds with
    no tool server at all (specs/teams-tool-access), and so does a save of one — only an
    agent actually assigned a tool needs the announcement to check it against.
    """
    _every_agent_names_a_known_model(definition, model_ids)
    _every_assigned_tool_is_announced(definition, announced_tools)


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
    definition: TeamDefinition, announced_tools: Collection[str] | None
) -> None:
    assigning = [agent for agent in definition.agents if agent.tools]
    if not assigning:
        return

    if announced_tools is None:
        agent = assigning[0]
        raise DefinitionRefused(
            f"agent {agent.key!r} is assigned tool(s) {sorted(agent.tools)}, but this "
            "module has no tool server to check them against — configure MARKET_MCP_URL, "
            "or save the team with no tools assigned"
        )

    known = set(announced_tools)
    for agent in assigning:
        unknown = sorted(tool for tool in agent.tools if tool not in known)
        if unknown:
            raise DefinitionRefused(
                f"agent {agent.key!r} is assigned tool(s) {unknown}, which the tool server "
                f"does not announce ({sorted(known)})"
            )


# Names of tools that change state outside this module. Empty today — market-mcp serves
# nothing but reads in this phase (proposal.md, "Faza 1 nie składa zleceń") — and this is
# where the first one is registered the day phase 2 adds it, rather than a check
# discovered only once an unattended team has already placed an order
# (specs/teams-schedules, "Harmonogram nad rewizją z narzędziami zapisującymi wymaga
# jawnego potwierdzenia"). A frozenset rather than a `Settings` field: this is a fact
# about market-mcp's own catalogue, not something an operator's `.env` should be able to
# quietly turn off.
STATE_CHANGING_TOOLS: frozenset[str] = frozenset()


def check_unattended(
    definition: TeamDefinition,
    *,
    unattended_ack: bool,
    state_changing_tools: Collection[str] = STATE_CHANGING_TOOLS,
) -> None:
    """Raises `DefinitionRefused` naming the agent and the tool, unless `unattended_ack`
    is set — the check a schedule or trigger runs against the revision it would put to
    work without an operator watching (specs/teams-schedules).

    `state_changing_tools` takes the module default so a test can prove the refusal path
    exists without market-mcp ever having announced such a tool for real.
    """
    if unattended_ack:
        return
    risky = set(state_changing_tools)
    for agent in definition.agents:
        named = sorted(tool for tool in agent.tools if tool in risky)
        if named:
            raise DefinitionRefused(
                f"agent {agent.key!r} carries state-changing tool(s) {named} — unattended "
                "work over this revision (a schedule or a trigger) needs an explicit "
                "acknowledgement (unattended_ack)"
            )


def check_trigger_tool(tool_name: str, *, announced_tools: Collection[str] | None) -> None:
    """The same shape of check `_every_assigned_tool_is_announced` runs for a team's own
    agents, run instead for the one tool a trigger's condition calls
    (specs/teams-triggers, "Warunek jest czytany narzędziami serwera narzędzi")."""
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
