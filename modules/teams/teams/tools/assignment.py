"""Which tools each agent gets, and the two refusals that stop a run before it starts.

The split against `client.py` is the one the spec draws: that file knows how to talk to
the server, this one knows what the definition asked for. Both refusals live here because
both are answers to the same question — "can this revision be run right now" — asked once,
before any agent is called, rather than discovered by the third agent halfway through
(specs/teams-tool-access).

What this module does **not** do: keep any description or parameter shape of its own. The
definition names tools by name and nothing else; every descriptor handed onward came out
of the session that will be used to call it, so a server that reworded a tool needs no
revision rewritten (specs/teams-tool-access, "Moduł nie trzyma kopii tego, co ogłasza
serwer narzędzi").
"""

from __future__ import annotations

from dataclasses import dataclass

from ..contract import TeamDefinition
from .client import ToolAccessError, ToolDescriptor, ToolServer


class ToolNoLongerAnnounced(ToolAccessError):
    """A revision names a tool the server does not publish any more.

    A refusal rather than a silent narrowing: the agent was given that tool on purpose,
    and running it without one is a different experiment than the one saved. The revision
    stays readable and unchanged — it is the run that is refused, not the definition
    (specs/teams-tool-access, "Narzędzie znika po stronie serwera").
    """


@dataclass(frozen=True)
class ToolPlan:
    """Every agent's tools, resolved once for the whole run.

    Resolved once rather than per agent so that two agents in the same run cannot be
    working from two different tool lists — the server is free to change between two
    reads, and a run whose halves disagree about what exists is not comparable with
    anything.
    """

    per_agent: dict[str, tuple[ToolDescriptor, ...]]

    def for_agent(self, key: str) -> tuple[ToolDescriptor, ...]:
        """Exactly what the definition assigned this agent, in the order it named them.

        A key the plan does not know is a programming error rather than a run-time
        condition — the plan is built from the same definition the run walks — so this
        raises `KeyError` rather than answering with an empty tuple, which would look
        like an agent that was assigned nothing.
        """
        return self.per_agent[key]


async def plan_tools(definition: TeamDefinition, server: ToolServer) -> ToolPlan:
    """Resolve the definition's tool names against what the server announces.

    Raises `ToolServerUnavailable` when a team that needs tools cannot reach the server,
    and `ToolNoLongerAnnounced` when it can but a named tool is gone. Both are
    `ToolAccessError`, which is what a run start refuses on.
    """
    assigned = {name for agent in definition.agents for name in agent.tools}
    if not assigned:
        # The server is not contacted at all — a team whose agents carry no tools runs
        # whether or not one is configured, reachable or awake (specs/teams-tool-access,
        # "Zespół, w którym nikt nie ma narzędzi"). Asking anyway would make an outage
        # elsewhere stop a run that never needed it.
        return ToolPlan({agent.key: () for agent in definition.agents})

    announced = await server.list_tools()
    by_name = {tool.name: tool for tool in announced}

    missing = sorted(assigned - by_name.keys())
    if missing:
        raise ToolNoLongerAnnounced(
            f"the tool server no longer announces {_and_list(missing)}, assigned to "
            f"{_and_list(_agents_wanting(definition, missing))}. The revision is unchanged "
            "and still readable — it is this run that is refused."
        )

    return ToolPlan(
        {agent.key: tuple(by_name[name] for name in agent.tools) for agent in definition.agents}
    )


def _agents_wanting(definition: TeamDefinition, tools: list[str]) -> list[str]:
    wanted = set(tools)
    return sorted(
        agent.key for agent in definition.agents if wanted.intersection(agent.tools)
    )


def _and_list(names: list[str]) -> str:
    """`a`, `a and b`, `a, b and c` — the message names every one of them rather than the
    first and a count, because the operator's next move is to fix each."""
    quoted = [f"{name!r}" for name in names]
    if len(quoted) <= 1:
        return "".join(quoted)
    return f"{', '.join(quoted[:-1])} and {quoted[-1]}"
