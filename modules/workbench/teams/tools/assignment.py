"""Which tools each agent gets, and the refusals that stop a run — or a save — before it proceeds. Every configured
server is queried, because a name found on one says nothing about whether a second announces it, which is a collision."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any

from ..config import Settings
from ..contract import TeamDefinition
from ..steps import node_tools
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
    """A revision names a tool no configured server publishes any more. A refusal rather than a silent
    narrowing: the agent was given that tool on purpose, and it is the run that is refused, not the definition."""


class AccountNotListed(ToolAccessError):
    """The revision trades on an account the gateway no longer lists. The run is refused before any agent,
    because every account call it would make would be refused one by one."""


ACCOUNT_ARGUMENT = "account_id"
# trading-mcp's names. The first moves every caller naming no account; the second changes the experiment mid-run.
# Its `account_id` is what it acts on, not where: switch_active_account's is the target, never injected.
ACCOUNT_MOVING_TOOLS = frozenset({"switch_active_account", "top_up_demo_account"})
_ACCOUNT_IS_THE_TARGET = frozenset({"switch_active_account"})


class AccountMovingToolOnAnAccount(ToolAccessError):
    """A revision trading on its own account assigns a tool that moves accounts. Refused at save, and again here,
    so a revision that slipped past the save cannot have the switch's target overwritten with its own account."""


class ToolNameCollision(ToolAccessError):
    """A revision names a tool more than one configured server announces. Refused rather than resolved by
    picking one: the definition carries only the name. The message names every server announcing it."""


@dataclass(frozen=True)
class ToolPlan:
    """Every agent's tools, resolved once for the whole run — and which server each came from, so a call
    reaches the right one without asking twice. Once, so two agents cannot work from two different lists."""

    per_agent: dict[str, tuple[ToolDescriptor, ...]]
    server_by_name: dict[str, ToolServer] = field(default_factory=dict)
    # tool name -> whether calling it could leave the account changed. Decided once here
    # rather than per call, off the same resolution the run was admitted on.
    writes_by_name: dict[str, bool] = field(default_factory=dict)
    # tool name -> the in-process source bound to this run. Separate from `server_by_name` because these
    # are called with *who* is calling: a local source acts on this team's rows and needs the agent.
    local_by_name: dict[str, Any] = field(default_factory=dict)
    # The revision's account, and the tools it is put into. The model never sees the argument: the schema
    # it is handed lost it, and `call` overwrites whatever it sent anyway — or drops it, with no account.
    account_id: str | None = None
    on_account: frozenset[str] = frozenset()
    # Which account the writes land on, for the trade rows: demo, or the live account.
    environment: str = "demo"

    def account_for(self, name: str) -> str | None:
        return self.account_id if name in self.on_account else None

    def for_agent(self, key: str) -> tuple[ToolDescriptor, ...]:
        """Exactly what the definition assigned this agent, in the order it named them. A key the plan does
        not know is a programming error, so this raises rather than answering with an empty tuple."""
        return self.per_agent[key]

    async def call(
        self, name: str, arguments: dict[str, Any], *, agent_key: str
    ) -> ToolOutcome:
        """Dispatch to the one source that announced `name`, with the assignment checked here rather than only when the
        tools were handed out. Refused as an outcome: a model that guessed a name made a correctable mistake."""
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
        if name in self.on_account:
            arguments = {k: v for k, v in arguments.items() if k != ACCOUNT_ARGUMENT}
            if self.account_id is not None:
                arguments[ACCOUNT_ARGUMENT] = self.account_id
        server = self.server_by_name.get(name)
        if server is None:
            # Unreachable through a run, whose plan is built from the same definition it walks — but a name
            # assigned and resolved is not the same fact as one that still has a source.
            return ToolOutcome(
                ToolOutcomeKind.UNAVAILABLE, f"no source announces {name}", 0
            )
        return await server.call(name, arguments)

    def moves_the_account(self, name: str) -> bool:
        """Whether calling `name` could leave the account changed — what a trade row and the daily count are written
        from. Unlike agent's method of the same name, this reads a plan resolved once rather than a live session."""
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
        # Every label, not the first two: an operator handed a partial list unconfigures one server and
        # meets the same refusal again.
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
    """Resolve the definition's tool names against every source's announcements, raising one of three `ToolAccessError`s.
    `memory` is the run this plan belongs to; absent, the in-process memory tools resolve but have no run to act in."""
    units = _units(definition)
    assigned = {name for _key, tools in units for name in tools}
    if definition.trading.environment == "live":
        _live_server_is_configured(registry, definition.trading.account_id)
    if not assigned:
        # Nothing is contacted at all — a team whose agents carry no tools runs whether or not any server
        # is configured. Asking anyway would make an outage elsewhere stop a run that never needed it.
        return ToolPlan(
            {key: () for key, _tools in units},
            environment=definition.trading.environment,
        )

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
        # No server has an address at all. Deliberately not "any server is unconfigured": with one
        # answering and the other unset, the name really is one nobody announces, and that refusal is true.
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
    account = definition.trading.account_id
    on_account = frozenset(
        name
        for name in assigned
        if name in server_by_name
        and server_by_name[name].can_move_the_account
        and ACCOUNT_ARGUMENT in resolution.by_name[name][0][1].input_schema.get("properties", {})
    )
    if account is not None and (moving := sorted(on_account & ACCOUNT_MOVING_TOOLS)):
        raise AccountMovingToolOnAnAccount(
            f"this team trades on account {account} and is assigned {and_list(moving)}, "
            "which would change the account for others, or the experiment while it runs"
        )
    # With no account the argument is still the plan's, not the model's: the order lands on the active one.
    on_account -= _ACCOUNT_IS_THE_TARGET
    if account is not None and on_account:
        await _check_listed(account, server_by_name[next(iter(on_account))])
    per_agent = {
        key: tuple(
            _without_account(resolution.by_name[name][0][1])
            if name in on_account
            else resolution.by_name[name][0][1]
            for name in tools
        )
        for key, tools in units
    }
    writes_by_name = {
        name: _moves_the_account(source_by_name[name], hits[0][1])
        for name, hits in resolution.by_name.items()
    }
    return ToolPlan(
        per_agent,
        server_by_name,
        writes_by_name,
        local_by_name,
        account_id=account,
        on_account=on_account,
        environment=definition.trading.environment,
    )


def _live_server_is_configured(registry: ToolServerRegistry, account: str | None) -> None:
    """Before anything else, tools or none: a team written for the live account has nothing to do anywhere else."""
    if not any(s.environment == "live" and s.configured for s in registry.servers.values()):
        raise ToolServerUnavailable(
            f"this team trades on the live account ({account}), and the live account's tool server is not "
            "configured (LIVE_TRADING_MCP_URL is unset)"
        )


def _without_account(tool: ToolDescriptor) -> ToolDescriptor:
    schema = dict(tool.input_schema)
    schema["properties"] = {
        k: v for k, v in schema.get("properties", {}).items() if k != ACCOUNT_ARGUMENT
    }
    if "required" in schema:
        schema["required"] = [k for k in schema["required"] if k != ACCOUNT_ARGUMENT]
    return replace(tool, input_schema=schema)


async def _check_listed(account: str, server: ToolServer) -> None:
    outcome = await server.call("list_accounts", {})
    if not outcome.ok:
        raise ToolServerUnavailable(
            f"could not confirm that account {account} exists: {outcome.text}"
        )
    listed = _listed_ids(outcome.text)
    if listed is None:
        raise ToolServerUnavailable(
            f"could not confirm that account {account} exists: list_accounts answered "
            f"{outcome.text[:200]!r}"
        )
    if account not in listed:
        raise AccountNotListed(
            f"this team trades on account {account}, which capital-gateway does not list "
            f"({and_list(sorted(str(a) for a in listed))})"
        )


def _listed_ids(text: str) -> list[str] | None:
    try:
        rows = json.loads(text).get("result")
        return [str(row["id"]) for row in rows]
    except (ValueError, AttributeError, KeyError, TypeError):
        return None


def _moves_the_account(server: ToolServer, tool: ToolDescriptor) -> bool:
    """The rule, in one place and written the conservative way: unknown on a server that can send orders reads as an
    order. The server gate keeps that from spreading, since nothing market-mcp publishes can reach the account."""
    return server.can_move_the_account and tool.read_only is not True


@dataclass(frozen=True)
class AnnouncedSnapshot:
    """What every configured tool server publishes right now, resolved for the save path — distinct from
    `ToolPlan`, because saving never needs a way to *call* anything."""

    # tool name -> the server label(s) announcing it; more than one is a collision.
    by_name: dict[str, list[str]]
    # labels of configured servers that could not be asked.
    unreachable: list[str]
    # Names every announcement that carried `readOnlyHint: true`. Deliberately the *positive* set: a name
    # missing here is one this module could not confirm is harmless, whichever of the three reasons it is.
    read_only: frozenset[str] = frozenset()
    # Servers this module knows about and has no address for. A name nobody announces while one of these
    # is unset reads differently from the same name with every server answering.
    unconfigured: tuple[str, ...] = ()


def _announcing(settings: Settings, local: Mapping[str, Any] | None) -> ToolServerRegistry:
    """Fresh sessions to every remote server, beside the in-process sources a run is given: the assembly adds the
    archives to the run's registry only, and one built from settings alone never names their tools."""
    registry = ToolServerRegistry.from_settings(settings)
    registry.local.update(local or {})
    return registry


async def _close_remote(registry: ToolServerRegistry) -> None:
    """Only the sessions this call opened — the borrowed local sources belong to the run's registry."""
    for server in registry.servers.values():
        await server.aclose()


async def announced_snapshot(
    settings: Settings, local: Mapping[str, Any] | None = None, *, environment: str = "demo"
) -> AnnouncedSnapshot:
    """The save path's view of every source a team of `environment` would be given: the servers it can reach, and the
    tools this process serves itself. Its own sessions, opened and closed inside this call, because a session left open
    when its task returns corrupts the scope stack."""
    everything = _announcing(settings, local)
    registry = everything.for_environment(environment)
    try:
        resolution = await _resolve_all(registry)
        return AnnouncedSnapshot(
            by_name={name: [label for label, _ in hits] for name, hits in resolution.by_name.items()},
            unreachable=sorted(resolution.failed),
            # `all(...)` rather than `any(...)`: a name two servers disagree about is not confirmed
            # read-only by anybody.
            read_only=frozenset(
                name
                for name, hits in resolution.by_name.items()
                if all(tool.read_only is True for _label, tool in hits)
            ),
            unconfigured=tuple(registry.unconfigured()),
        )
    finally:
        await _close_remote(everything)


async def announced_tools_by_server(
    settings: Settings, local: Mapping[str, Any] | None = None
) -> list[ToolDescriptor]:
    """Every tool every configured server publishes right now — the shape `GET /tools` wants. Raises naming
    whichever server could not be asked: a partial list is not the complete catalogue the picker needs. The demo view:
    the live account's tool server announces the same names, and a picker listing each twice says nothing more."""
    everything = _announcing(settings, local)
    registry = everything.for_environment("demo")
    try:
        resolution = await _resolve_all(registry)
        if resolution.failed:
            names = and_list(sorted(resolution.failed))
            details = "; ".join(str(err) for err in resolution.failed.values())
            raise ToolServerUnavailable(f"{names} could not be reached: {details}")
        return [tool for hits in resolution.by_name.values() for _label, tool in hits]
    finally:
        await _close_remote(everything)


def _units(definition: TeamDefinition) -> list[tuple[str, tuple[str, ...]]]:
    return [(key, tools) for _kind, key, tools in node_tools(definition)]


def _agents_wanting(definition: TeamDefinition, tools: list[str]) -> list[str]:
    wanted = set(tools)
    return sorted(key for key, assigned in _units(definition) if wanted.intersection(assigned))


def and_list(names: list[str]) -> str:
    """`a`, `a and b`, `a, b and c` — the message names every one rather than the first and a count, because
    the operator's next move is to fix each. Public because the save path lists them too."""
    quoted = [f"{name!r}" for name in names]
    if len(quoted) <= 1:
        return "".join(quoted)
    return f"{', '.join(quoted[:-1])} and {quoted[-1]}"
