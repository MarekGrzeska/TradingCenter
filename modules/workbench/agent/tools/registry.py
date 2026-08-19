"""Every source of tools this surface knows about, behind one door.

It is a drop-in for a single `ToolServer`: same `configured`, same `list_tools`, same
`call`, same `aclose` — so nothing above this package had to learn that there is more than
one source now.

**Two of them are servers on a network and one is not.** The archive's tools and the
account's are reached over MCP; the team tools are a layer in this same process, handed in
as `local_sources` because building one needs the application object this registry has no
business knowing about (`workbench/team_tools.py`). Everything below treats the three
alike, which is the point of the seam.

**Independence is the property worth stating**, because it is what `specs/agent-tool-access`
asks for and what a union would quietly lose: one server being unconfigured, unreachable
or slow costs the model that server's tools and nothing else. A turn keeps whatever
answered — and a local source answers whatever the network is doing.

A name announced by two sources is refused rather than resolved by picking one. It cannot
happen with the three that exist — one reads candles, one builds teams, one moves the
account — and if it ever does, guessing would send an operator's "run it" to whichever
source happened to be first in a dictionary.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from ..config import Settings
from .client import ToolDescriptor, ToolOutcome, ToolOutcomeKind, ToolServer

log = logging.getLogger(__name__)

# A source is anything with this registry's own five members. `ToolServer` is one;
# `workbench.team_tools.LocalTeamsTools` is the other, and neither knows about the other.
ToolSource = Any


class ToolServerRegistry:
    def __init__(self, servers: list[ToolSource]) -> None:
        self._servers = servers
        self._owner: dict[str, ToolSource] = {}

    @classmethod
    def from_settings(
        cls, settings: Settings, local_sources: list[ToolSource] | None = None
    ) -> ToolServerRegistry:
        """The two network servers, plus whatever the assembly hands in.

        `local_sources` defaults to none so a test wanting the network half alone builds
        it in one line — and so this class stays buildable from settings, which is all it
        can know by itself.
        """
        return cls(
            [
                ToolServer(settings, prefix="market_mcp"),
                # The one whose writes land on the account. No operator identity: the
                # account is one and shared, there is nobody in whose name it could be
                # moved differently, and trading-mcp reads no such header.
                ToolServer(settings, prefix="trading_mcp", can_move_the_account=True),
                *(local_sources or []),
            ]
        )

    @property
    def configured(self) -> bool:
        return any(server.configured for server in self._servers)

    async def aclose(self) -> None:
        for server in self._servers:
            await server.aclose()

    async def list_tools(self, operator_principal: str | None = None) -> list[ToolDescriptor]:
        """Every tool every configured source publishes right now.

        Asked of all of them at once — one slow server would otherwise make the model
        wait for it before the turn could start, and the whole point of asking before the
        first model call is that the set is fixed for the turn.
        """
        configured = [server for server in self._servers if server.configured]
        if not configured:
            return []

        answers = await asyncio.gather(
            *(server.list_tools(operator_principal) for server in configured)
        )

        self._owner = {}
        tools: list[ToolDescriptor] = []
        for server, published in zip(configured, answers, strict=True):
            for tool in published:
                if tool.name in self._owner:
                    log.warning(
                        "%s and %s both announce %r — it is offered to the model by "
                        "neither, because nothing here can say which was meant",
                        self._owner[tool.name].label,
                        server.label,
                        tool.name,
                    )
                    continue
                self._owner[tool.name] = server
                tools.append(tool)
        return tools

    def moves_the_account(self, name: str) -> bool:
        """Whether this name belongs to a tool that could change the account. Answered
        from the descriptors `list_tools` already read, so the caller can write the trace
        before dispatching (specs/agent-trading).

        A name nobody announced is not account-moving: `call` will refuse it without
        sending anything, so there is nothing to leave a trace of.
        """
        server = self._owner.get(name)
        return server is not None and server.moves_the_account(name)

    async def call(
        self, name: str, arguments: dict, operator_principal: str | None = None
    ) -> ToolOutcome:
        """Dispatch to the source that announced this name.

        A name nobody announced is an outcome rather than an exception, like every other
        failure on this seam: the model asked for something that is not there, and the
        turn continues with that as its answer.
        """
        server = self._owner.get(name)
        if server is None:
            return ToolOutcome(
                ToolOutcomeKind.UNAVAILABLE,
                f"no configured tool source announces {name!r}, so this call was not made",
                0,
            )
        return await server.call(name, arguments, operator_principal)
