"""Which tools each agent gets, and the refusals that stop a run — or a save — before
it proceeds.

The split against `client.py` is the one the spec draws: that file knows how to talk to
a server, this one knows what the definition asked for and how the module's *several*
servers reconcile into one answer. Every refusal here answers one question — "can this
revision be run (or saved) right now" — asked once, before any agent is called, rather
than discovered by the third agent halfway through (specs/teams-tool-access).

What this module does **not** do: keep any description or parameter shape of its own. The
definition names tools by name and nothing else; every descriptor handed onward came out
of the session that will be used to call it, so a server that reworded a tool needs no
revision rewritten (specs/teams-tool-access, "Moduł nie trzyma kopii tego, co ogłasza
serwer narzędzi").

**Resolving a name against more than one server** is the addition this phase makes, and
it is the one place the two servers' announcements ever meet. `_resolve_all` queries
every *configured* server — never fewer, because a name found on one server says nothing
about whether a second one also announces it, and that is exactly the fact a collision
refusal needs (specs/teams-tool-access, "Ta sama nazwa narzędzia z dwóch serwerów jest
odmową"). A server this module never needed anything from can still fail that query —
its failure is folded away rather than raised, as long as every *assigned* name was found
on a server that did answer (specs/teams-tool-access, "Nieosiągalny jest tylko serwer, z
którego nikt nic nie ma").
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from ..config import Settings
from ..contract import TeamDefinition
from .client import (
    ToolAccessError,
    ToolDescriptor,
    ToolOutcome,
    ToolServer,
    ToolServerRegistry,
    ToolServerUnavailable,
)


class ToolNoLongerAnnounced(ToolAccessError):
    """A revision names a tool no configured server publishes any more.

    A refusal rather than a silent narrowing: the agent was given that tool on purpose,
    and running it without one is a different experiment than the one saved. The revision
    stays readable and unchanged — it is the run that is refused, not the definition
    (specs/teams-tool-access, "Narzędzie znika po stronie serwera").
    """


class ToolNameCollision(ToolAccessError):
    """A revision names a tool that more than one configured server announces.

    Refused rather than resolved by picking one: the definition carries only the name,
    so there is nothing in it that could say which server was meant
    (specs/teams-tool-access, "Ta sama nazwa narzędzia z dwóch serwerów jest odmową").
    """


@dataclass(frozen=True)
class ToolPlan:
    """Every agent's tools, resolved once for the whole run — and which server each one
    came from, so a call during the run reaches the right one without asking twice.

    Resolved once rather than per agent so that two agents in the same run cannot be
    working from two different tool lists — a server is free to change between two
    reads, and a run whose halves disagree about what exists is not comparable with
    anything.
    """

    per_agent: dict[str, tuple[ToolDescriptor, ...]]
    server_by_name: dict[str, ToolServer] = field(default_factory=dict)

    def for_agent(self, key: str) -> tuple[ToolDescriptor, ...]:
        """Exactly what the definition assigned this agent, in the order it named them.

        A key the plan does not know is a programming error rather than a run-time
        condition — the plan is built from the same definition the run walks — so this
        raises `KeyError` rather than answering with an empty tuple, which would look
        like an agent that was assigned nothing.
        """
        return self.per_agent[key]

    async def call(self, name: str, arguments: dict[str, Any]) -> ToolOutcome:
        """Dispatch to the one server that announced `name` — collision-free by
        construction, since `plan_tools` refuses a run before this method exists for a
        name two servers both claim."""
        return await self.server_by_name[name].call(name, arguments)


@dataclass(frozen=True)
class _Resolution:
    # tool name -> [(server label, descriptor), ...]; more than one entry is a collision.
    by_name: dict[str, list[tuple[str, ToolDescriptor]]]
    # server label -> the error that server's query raised.
    failed: dict[str, ToolServerUnavailable]


async def _resolve_all(registry: ToolServerRegistry) -> _Resolution:
    configured = registry.configured()
    results = await asyncio.gather(
        *(_list_or_fail(server) for server in configured)
    )

    by_name: dict[str, list[tuple[str, ToolDescriptor]]] = {}
    failed: dict[str, ToolServerUnavailable] = {}
    for server, outcome in zip(configured, results, strict=True):
        if isinstance(outcome, ToolServerUnavailable):
            failed[server.label] = outcome
            continue
        for tool in outcome:
            by_name.setdefault(tool.name, []).append((server.label, tool))
    return _Resolution(by_name, failed)


async def _list_or_fail(server: ToolServer) -> list[ToolDescriptor] | ToolServerUnavailable:
    try:
        return await server.list_tools()
    except ToolServerUnavailable as err:
        return err


def _collisions(resolution: _Resolution, names: set[str]) -> dict[str, list[str]]:
    return {
        name: [label for label, _ in hits]
        for name, hits in resolution.by_name.items()
        if name in names and len(hits) > 1
    }


def _raise_for_collisions(resolution: _Resolution, names: set[str]) -> None:
    collisions = _collisions(resolution, names)
    if collisions:
        lines = "; ".join(
            f"{name!r} ({' and '.join(labels)})" for name, labels in sorted(collisions.items())
        )
        raise ToolNameCollision(f"more than one tool server announces: {lines}")


async def plan_tools(definition: TeamDefinition, registry: ToolServerRegistry) -> ToolPlan:
    """Resolve the definition's tool names against every configured server's
    announcements.

    Raises `ToolServerUnavailable` when an assigned name could not be confirmed because
    some server could not be asked, `ToolNameCollision` when two servers both announce an
    assigned name, and `ToolNoLongerAnnounced` when every server answered and none of
    them announce it. All three are `ToolAccessError`, which is what a run start refuses
    on.
    """
    assigned = {name for agent in definition.agents for name in agent.tools}
    if not assigned:
        # No server is contacted at all — a team whose agents carry no tools runs
        # whether or not any server is configured, reachable or awake (specs/
        # teams-tool-access, "Zespół, w którym nikt nie ma narzędzi"). Asking anyway
        # would make an outage elsewhere stop a run that never needed it.
        return ToolPlan({agent.key: () for agent in definition.agents})

    if not registry.configured():
        raise ToolServerUnavailable(
            "no tool server is configured, so the tool(s) this definition assigns "
            "could not be checked"
        )

    resolution = await _resolve_all(registry)
    _raise_for_collisions(resolution, assigned)

    missing = sorted(name for name in assigned if name not in resolution.by_name)
    if missing:
        if resolution.failed:
            raise ToolServerUnavailable(
                f"could not confirm tool(s) {_and_list(missing)} — "
                f"{_and_list(sorted(resolution.failed))} could not be reached: "
                f"{'; '.join(str(err) for err in resolution.failed.values())}"
            )
        raise ToolNoLongerAnnounced(
            f"no configured tool server announces {_and_list(missing)}, assigned to "
            f"{_and_list(_agents_wanting(definition, missing))}. The revision is unchanged "
            "and still readable — it is this run that is refused."
        )

    servers_by_label = {server.label: server for server in registry.configured()}
    server_by_name = {
        name: servers_by_label[hits[0][0]] for name, hits in resolution.by_name.items()
    }
    per_agent = {
        agent.key: tuple(resolution.by_name[name][0][1] for name in agent.tools)
        for agent in definition.agents
    }
    return ToolPlan(per_agent, server_by_name)


@dataclass(frozen=True)
class AnnouncedSnapshot:
    """What every configured tool server publishes right now, resolved for the save
    path — `validation.py`'s own shape, distinct from `ToolPlan` because saving never
    needs a way to *call* anything.
    """

    # tool name -> the server label(s) announcing it; more than one is a collision.
    by_name: dict[str, list[str]]
    # labels of configured servers that could not be asked.
    unreachable: list[str]


async def announced_snapshot(settings: Settings) -> AnnouncedSnapshot | None:
    """The save path's view of every configured server, or `None` when none is
    configured at all.

    **A registry of its own, opened and closed inside this call, rather than the
    long-lived one on `app.state`.** Measured, not preferred: the streamable-http
    transport holds its halves in anyio task groups, and a session opened inside a
    request's task and left open when that task returns corrupts anyio's scope stack —
    "Attempted to exit a cancel scope that isn't the current task's current cancel
    scope", raised on the way out of the request rather than anywhere near the cause. An
    operator pressing a button is not a rate that makes one connection per press worth
    avoiding; a run, which is where the shared registry belongs, holds its own task for
    as long as its sessions live.
    """
    registry = ToolServerRegistry.from_settings(settings)
    try:
        if not registry.configured():
            return None
        resolution = await _resolve_all(registry)
        return AnnouncedSnapshot(
            by_name={name: [label for label, _ in hits] for name, hits in resolution.by_name.items()},
            unreachable=sorted(resolution.failed),
        )
    finally:
        await registry.aclose()


async def announced_tools_by_server(settings: Settings) -> list[ToolDescriptor]:
    """Every tool every configured server publishes right now — the shape `GET /tools`
    wants. Raises `ToolServerUnavailable` naming whichever configured server(s) could
    not be asked: a partial list is not the complete catalogue the picker needs, and
    saying so as an outage is truer than answering with what could be confirmed
    (specs/trading-mcp-tools; mirrors the single-server "200 empty / 200 tools / 503"
    contract `routers/tools.py` already documents, generalized to more than one server).
    """
    registry = ToolServerRegistry.from_settings(settings)
    try:
        if not registry.configured():
            return []
        resolution = await _resolve_all(registry)
        if resolution.failed:
            names = _and_list(sorted(resolution.failed))
            details = "; ".join(str(err) for err in resolution.failed.values())
            raise ToolServerUnavailable(f"{names} could not be reached: {details}")
        return [tool for hits in resolution.by_name.values() for _label, tool in hits]
    finally:
        await registry.aclose()


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
