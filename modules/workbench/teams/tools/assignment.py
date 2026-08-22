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
it is the one place the configured servers' announcements ever meet. `_resolve_all` queries
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
    ToolOutcomeKind,
    ToolServer,
    ToolServerRegistry,
    ToolServerUnavailable,
)
from .memory import MemoryScope


def _assigned_list(assigned: set[str]) -> str:
    if not assigned:
        return "It was assigned none."
    return f"It has: {', '.join(sorted(assigned))}."


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
    so there is nothing in it that could say which server was meant. The message names
    every server announcing it, however many that is
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
    # tool name -> whether calling it could leave the account changed. Decided once here
    # rather than per call, off the same resolution the run was admitted on.
    writes_by_name: dict[str, bool] = field(default_factory=dict)
    # tool name -> the in-process source bound to this run. Separate from `server_by_name`
    # because these are called with *who* is calling: a local source acts on this team's
    # own rows and needs the agent, while a remote server authenticates as the module and
    # would have nothing to do with the name of an agent inside it.
    local_by_name: dict[str, Any] = field(default_factory=dict)

    def for_agent(self, key: str) -> tuple[ToolDescriptor, ...]:
        """Exactly what the definition assigned this agent, in the order it named them.

        A key the plan does not know is a programming error rather than a run-time
        condition — the plan is built from the same definition the run walks — so this
        raises `KeyError` rather than answering with an empty tuple, which would look
        like an agent that was assigned nothing.
        """
        return self.per_agent[key]

    async def call(
        self, name: str, arguments: dict[str, Any], *, agent_key: str
    ) -> ToolOutcome:
        """Dispatch to the one source that announced `name` — collision-free by
        construction, since `plan_tools` refuses a run before this method exists for a
        name two of them both claim.

        **The assignment is checked here, not only when the tools were handed out.** What
        the model was offered is protection against a mistake; it is no protection against
        an attempt, and the model writes the name itself — from another tool's description,
        from a predecessor's briefing, or out of habit. While every announced tool only
        read, the difference was theoretical. It stopped being theoretical the moment one
        agent may write something another may only read (specs/teams-tool-access, "Agent
        dostaje narzędzia wskazane w definicji, a nie wszystkie").

        Refused as an outcome rather than raised, like `TradeGuard`'s refusals: the model
        gets a sentence it can act on, the attempt lands in `tool_calls`, and the run
        carries on. A model that guessed a name made a mistake worth correcting, not one
        worth ending the experiment over.
        """
        assigned = {tool.name for tool in self.per_agent.get(agent_key, ())}
        if name not in assigned:
            return ToolOutcome(
                ToolOutcomeKind.REFUSED,
                f"{name} is not one of the tools assigned to {agent_key}. "
                f"{_assigned_list(assigned)}",
                0,
            )
        local = self.local_by_name.get(name)
        if local is not None:
            return await local.call(name, arguments, agent_key=agent_key)
        server = self.server_by_name.get(name)
        if server is None:
            # Unreachable through a run, whose plan is built from the same definition it
            # walks — but a name assigned and resolved is not the same fact as a name that
            # still has a source, and answering is cheaper than assuming.
            return ToolOutcome(
                ToolOutcomeKind.UNAVAILABLE, f"no source announces {name}", 0
            )
        return await server.call(name, arguments)

    def moves_the_account(self, name: str) -> bool:
        """Whether calling `name` could leave the account changed — the question a trade
        row and the daily count are both written from.

        A name the plan does not know answers `False`: `call` cannot reach any server
        with it, so nothing can land. That is the one place this differs from
        `agent/tools/client.py`'s method of the same name, which answers `True` there —
        and the difference is real rather than drift: agent asks a live session whose
        tool list is dropped every time the connection breaks, so its "unknown name"
        genuinely means "cannot tell right now". A plan is resolved once, before the run
        is admitted, and never dropped.

        Everything else about the two is deliberately identical, including the reading
        that made them differ until 18 August 2026 — see `_moves_the_account` below.
        """
        return self.writes_by_name.get(name, False)


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
        # Every label, not the first two: an operator handed a partial list unconfigures
        # one server and meets the same refusal again (specs/teams-tool-access, "Ta sama
        # nazwa narzędzia z dwóch serwerów jest odmową").
        lines = "; ".join(
            f"{name!r} ({and_list(labels)})" for name, labels in sorted(collisions.items())
        )
        raise ToolNameCollision(f"more than one tool server announces: {lines}")


async def plan_tools(
    definition: TeamDefinition,
    registry: ToolServerRegistry,
    *,
    memory: MemoryScope | None = None,
) -> ToolPlan:
    """Resolve the definition's tool names against every source's announcements.

    Raises `ToolServerUnavailable` when an assigned name could not be confirmed because
    some server could not be asked or has no address at all, `ToolNameCollision` when more
    than one source announces an assigned name, and `ToolNoLongerAnnounced` when every
    source answered and none of them announce it. All three are `ToolAccessError`, which is
    what a run start refuses on.

    `memory` is the run this plan belongs to. Absent — as it is on every save-time path —
    the in-process memory tools still resolve and still count as announced; they simply
    have no run to act in, and answer as unavailable if called.
    """
    assigned = {name for agent in definition.agents for name in agent.tools}
    if not assigned:
        # Nothing is contacted at all — a team whose agents carry no tools runs whether or
        # not any server is configured, reachable or awake (specs/teams-tool-access,
        # "Zespół, w którym nikt nie ma narzędzi"). Asking anyway would make an outage
        # elsewhere stop a run that never needed it.
        return ToolPlan({agent.key: () for agent in definition.agents})

    resolution = await _resolve_all(registry)
    _raise_for_collisions(resolution, assigned)

    missing = sorted(name for name in assigned if name not in resolution.by_name)
    if missing:
        if resolution.failed:
            raise ToolServerUnavailable(
                f"could not confirm tool(s) {and_list(missing)} — "
                f"{and_list(sorted(resolution.failed))} could not be reached: "
                f"{'; '.join(str(err) for err in resolution.failed.values())}"
            )
        # No server has an address at all — the case an early `not registry.configured()`
        # check used to answer, which stopped being reachable once a source this process
        # serves itself joined the registry: that one is always configured. So the question
        # became "is any *server* configured", and the answer names the ones that are not
        # (specs/teams-tool-access, "Brak serwera narzędzi zatrzymuje przebieg").
        #
        # Deliberately not "any server is unconfigured": with one server answering and the
        # other unset, the name really is one nobody announces, and the refusal below is
        # the true one. Pointing at the unset server there would send the operator to a
        # setting to fix a tool the configured server had already declined to have.
        if not registry.remote() and (unconfigured := registry.unconfigured()):
            raise ToolServerUnavailable(
                f"could not confirm tool(s) {and_list(missing)}, assigned to "
                f"{and_list(_agents_wanting(definition, missing))} — "
                f"{and_list(unconfigured)} {'is' if len(unconfigured) == 1 else 'are'} "
                "not configured"
            )
        raise ToolNoLongerAnnounced(
            f"no configured tool server announces {and_list(missing)}, assigned to "
            f"{and_list(_agents_wanting(definition, missing))}. The revision is unchanged "
            "and still readable — it is this run that is refused."
        )

    sources_by_label = {source.label: source for source in registry.configured()}
    source_by_name = {
        name: sources_by_label[hits[0][0]] for name, hits in resolution.by_name.items()
    }
    local_labels = set(registry.local)
    local_by_name = {
        name: (source.bound(memory) if memory is not None else source)
        for name, source in source_by_name.items()
        if source.label in local_labels
    }
    server_by_name = {
        name: source
        for name, source in source_by_name.items()
        if source.label not in local_labels
    }
    per_agent = {
        agent.key: tuple(resolution.by_name[name][0][1] for name in agent.tools)
        for agent in definition.agents
    }
    writes_by_name = {
        name: _moves_the_account(source_by_name[name], hits[0][1])
        for name, hits in resolution.by_name.items()
    }
    return ToolPlan(per_agent, server_by_name, writes_by_name, local_by_name)


def _moves_the_account(server: ToolServer, tool: ToolDescriptor) -> bool:
    """The rule, in one place and written the conservative way.

    `read_only is not True`, not `read_only is False`. A tool carrying no annotation at
    all is *unknown*, and unknown on a server that can send orders has to read as an
    order: otherwise the first tool trading-mcp publishes without one travels with no row
    in `trades` and no charge against `TradingLimits` — a silent way round `TradeGuard`
    rather than a missing feature. This module read it the other way until 18 August
    2026, when an audit found `agent` deciding the same question from the same
    `readOnlyHint` and answering the opposite. They are kept identical on purpose; the
    twin is `ToolServer.moves_the_account` in `agent/tools/client.py`.

    The server gate is what keeps that conservatism from spreading: an unannotated tool
    on market-mcp still reads as what it is, because nothing market-mcp publishes can
    reach the account (specs/teams-trading).
    """
    return server.can_move_the_account and tool.read_only is not True


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
    # Names every announcement of which carried `readOnlyHint: true`. Deliberately the
    # *positive* set: a name missing here is one this module could not confirm is
    # harmless — because it announced itself as a write (trading-mcp's `place_order`),
    # because it carried no annotation, or because nobody answered — and unattended work
    # over any of those needs the operator to say so (specs/teams-schedules, "Harmonogram
    # nad rewizją z narzędziami zapisującymi wymaga jawnego potwierdzenia").
    read_only: frozenset[str] = frozenset()
    # Servers this module knows about and has no address for. A name nobody announces
    # while one of these is unset reads differently from the same name with every server
    # answering, and the refusal says which (`validation.py`).
    unconfigured: tuple[str, ...] = ()
    # Labels of the servers that *do* have an address — empty means every tool in
    # `by_name` came from this process itself.
    configured_servers: tuple[str, ...] = ()


async def announced_snapshot(settings: Settings) -> AnnouncedSnapshot:
    """The save path's view of every source: the servers it can reach, and the tools this
    process serves itself.

    It no longer answers `None`. It used to, for "no tool server is configured at all",
    and that stopped being a state a snapshot could be in once a source living inside this
    process joined the registry — there is always something announcing something. What the
    `None` said is now said by `configured_servers` being empty, which is a narrower claim
    and the true one.

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
        resolution = await _resolve_all(registry)
        return AnnouncedSnapshot(
            by_name={name: [label for label, _ in hits] for name, hits in resolution.by_name.items()},
            unreachable=sorted(resolution.failed),
            # `all(...)` rather than `any(...)`: a name two servers disagree about is not
            # confirmed read-only by anybody. (It is also a collision, refused elsewhere —
            # but this set is read on its own, so it does not lean on that.)
            read_only=frozenset(
                name
                for name, hits in resolution.by_name.items()
                if all(tool.read_only is True for _label, tool in hits)
            ),
            unconfigured=tuple(registry.unconfigured()),
            configured_servers=tuple(server.label for server in registry.remote()),
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
        resolution = await _resolve_all(registry)
        if resolution.failed:
            names = and_list(sorted(resolution.failed))
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


def and_list(names: list[str]) -> str:
    """`a`, `a and b`, `a, b and c` — the message names every one of them rather than the
    first and a count, because the operator's next move is to fix each. Public because
    the save path refuses in `validation.py` and has the same reason to list them all."""
    quoted = [f"{name!r}" for name in names]
    if len(quoted) <= 1:
        return "".join(quoted)
    return f"{', '.join(quoted[:-1])} and {quoted[-1]}"
