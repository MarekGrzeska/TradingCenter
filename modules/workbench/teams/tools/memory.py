"""The two tools a team uses to remember something, served by this process as a source rather than a server: no address,
no session to lose. Announcing touches no database, so the save-time paths publish these names with no connection."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import asyncpg

from .. import store
from ..contract import MEMORY_ENTRY_MAX_CHARS, MEMORY_READ_LIMIT, MEMORY_WRITES_PER_RUN
from .client import ToolDescriptor, ToolOutcome, ToolOutcomeKind

log = logging.getLogger(__name__)

LABEL = "team-memory"

READ_TOOL = "memory_read"
WRITE_TOOL = "memory_write"

# The descriptions are the only thing a model ever learns about these tools, so both state what the tool
# will refuse and why — a ceiling left unsaid turns a refusal into a surprise the model explains by guessing.
MEMORY_TOOLS: tuple[ToolDescriptor, ...] = (
    ToolDescriptor(
        name=READ_TOOL,
        description=(
            "Read what this team has learned in earlier runs. Notes are shared by the "
            "whole team and outlive every run and revision. Returns the "
            f"{MEMORY_READ_LIMIT} newest notes, newest first, and says so when there are "
            "more than that. A team that has never written a note reads empty, which is "
            "normal and not an error. Takes no arguments."
        ),
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        read_only=True,
    ),
    ToolDescriptor(
        name=WRITE_TOOL,
        description=(
            "Leave one note for later runs of this team. Write a conclusion worth acting "
            "on next time, not a summary of this run — the run's own trace already holds "
            "that. A note cannot be edited or deleted afterwards: correct an earlier note "
            "by writing another one, and only the operator removes anything. Refused when "
            f"the note is empty or longer than {MEMORY_ENTRY_MAX_CHARS} characters, and "
            f"when this run has already written {MEMORY_WRITES_PER_RUN} notes. A refusal "
            "does not stop the run."
        ),
        input_schema={
            "type": "object",
            "properties": {"content": {"type": "string"}},
            "required": ["content"],
            "additionalProperties": False,
        },
        read_only=False,
    ),
)

MEMORY_TOOL_NAMES: frozenset[str] = frozenset(tool.name for tool in MEMORY_TOOLS)


@dataclass(frozen=True)
class MemoryScope:
    """Which team is remembering, on whose behalf, and in which run. Carried from the run start rather than
    read off the definition: the same definition can stand under two names for two operators."""

    team_id: int
    owner_principal: str
    run_id: int


class MemoryToolSource:
    """The unbound source: announces, and refuses to act without a run."""

    label = LABEL
    can_move_the_account = False

    def __init__(self, pool: asyncpg.Pool | None = None) -> None:
        self._pool = pool

    @property
    def configured(self) -> bool:
        """Always. There is no setting whose absence turns memory off — a team assigned no memory tool does
        not see it, and that is the whole of the switch."""
        return True

    async def list_tools(self) -> list[ToolDescriptor]:
        return list(MEMORY_TOOLS)

    def bound(self, scope: MemoryScope) -> BoundMemoryTools:
        return BoundMemoryTools(self._pool, scope)

    async def call(
        self, name: str, arguments: dict[str, Any], *, agent_key: str | None = None
    ) -> ToolOutcome:
        """Reached only when something called memory outside a run — the plan binds a
        scope whenever it has one. Answered rather than raised, like every other call."""
        log.warning("%s was called with no run bound to it", name)
        return ToolOutcome(
            ToolOutcomeKind.UNAVAILABLE,
            f"{name} is only available inside a team run, and this call was made outside one",
            0,
        )

    async def aclose(self) -> None:
        """Nothing of its own to close — the pool belongs to the application."""


class BoundMemoryTools:
    """One run's view of its team's memory."""

    label = LABEL
    can_move_the_account = False

    def __init__(self, pool: asyncpg.Pool | None, scope: MemoryScope) -> None:
        self._pool = pool
        self._scope = scope

    async def call(self, name: str, arguments: dict[str, Any], *, agent_key: str) -> ToolOutcome:
        if self._pool is None:
            return ToolOutcome(
                ToolOutcomeKind.UNAVAILABLE,
                f"{name} could not reach this team's memory",
                0,
            )
        if name == READ_TOOL:
            return await self._read()
        if name == WRITE_TOOL:
            return await self._write(arguments, agent_key=agent_key)
        return ToolOutcome(
            ToolOutcomeKind.UNAVAILABLE, f"{name} is not a team-memory tool", 0
        )

    async def _read(self) -> ToolOutcome:
        scope = self._scope
        async with self._pool.acquire() as conn:  # type: ignore[union-attr]
            rows, total = await store.list_memories(
                conn,
                team_id=scope.team_id,
                owner_principal=scope.owner_principal,
                limit=MEMORY_READ_LIMIT,
            )
        if not rows:
            return ToolOutcome(
                ToolOutcomeKind.OK, "This team has not written any notes yet.", 0
            )
        lines = [
            f"[{row['created_at']:%Y-%m-%d %H:%M} · {row['author_agent_key']}] {row['content']}"
            for row in rows
        ]
        if total > len(rows):
            # Never a silent cut: a model reading a truncated memory as the whole of it
            # would draw a conclusion from an absence it invented (specs/teams-memory).
            lines.append(
                f"({len(rows)} newest of {total} notes shown; the older ones are not included.)"
            )
        return ToolOutcome(ToolOutcomeKind.OK, "\n".join(lines), 0)

    async def _write(self, arguments: dict[str, Any], *, agent_key: str) -> ToolOutcome:
        content = arguments.get("content")
        if not isinstance(content, str) or not content.strip():
            return ToolOutcome(
                ToolOutcomeKind.REFUSED, "A note needs some content to be worth keeping.", 0
            )
        content = content.strip()
        if len(content) > MEMORY_ENTRY_MAX_CHARS:
            return ToolOutcome(
                ToolOutcomeKind.REFUSED,
                f"That note is {len(content)} characters and the limit is "
                f"{MEMORY_ENTRY_MAX_CHARS}. Write the conclusion rather than the reasoning.",
                0,
            )

        scope = self._scope
        async with self._pool.acquire() as conn:  # type: ignore[union-attr]
            # Counted in the database rather than in this object: agents in one run work concurrently and
            # each holds its own bound instance, so a counter here would let two pass the ceiling together.
            written = await store.count_memories_for_run(conn, run_id=scope.run_id)
            if written >= MEMORY_WRITES_PER_RUN:
                return ToolOutcome(
                    ToolOutcomeKind.REFUSED,
                    f"This run has already written {written} notes, which is the limit of "
                    f"{MEMORY_WRITES_PER_RUN}. Nothing more will be kept from this run.",
                    0,
                )
            entry = await store.add_memory(
                conn,
                team_id=scope.team_id,
                owner_principal=scope.owner_principal,
                author_agent_key=agent_key,
                run_id=scope.run_id,
                content=content,
            )

        if entry is None:
            return ToolOutcome(
                ToolOutcomeKind.UNAVAILABLE, "This team's memory could not be written to", 0
            )
        return ToolOutcome(
            ToolOutcomeKind.OK, "Noted. Later runs of this team will read it.", 0
        )

    async def aclose(self) -> None:
        """Nothing of its own to close — the pool belongs to the application."""
