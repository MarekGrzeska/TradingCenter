"""Every tool server this module knows about, behind one door.

A deliberate twin of `teams/tools/client.py`'s registry, copied rather than shared (no
library between modules). It is a drop-in for a single `ToolServer`: same `configured`,
same `list_tools`, same `call`, same `aclose` — so nothing above this package had to
learn that there is more than one server now.

**Independence is the property worth stating**, because it is what `specs/agent-tool-access`
asks for and what a union would quietly lose: one server being unconfigured, unreachable
or slow costs the model that server's tools and nothing else. A turn keeps whatever
answered.

A name announced by two servers is refused rather than resolved by picking one. It cannot
happen with the two that exist — one reads candles, the other builds teams — and if it
ever does, guessing would send an operator's "run it" to whichever server happened to be
first in a dictionary.
"""

from __future__ import annotations

import asyncio
import logging

from ..config import Settings
from .client import ToolDescriptor, ToolOutcome, ToolOutcomeKind, ToolServer

log = logging.getLogger(__name__)


class ToolServerRegistry:
    def __init__(self, servers: list[ToolServer]) -> None:
        self._servers = servers
        self._owner: dict[str, ToolServer] = {}

    @classmethod
    def from_settings(cls, settings: Settings) -> ToolServerRegistry:
        return cls(
            [
                ToolServer(settings, prefix="market_mcp"),
                # The one that acts for a person rather than for this module.
                ToolServer(settings, prefix="teams_mcp", forwards_operator_token=True),
            ]
        )

    @property
    def configured(self) -> bool:
        return any(server.configured for server in self._servers)

    async def aclose(self) -> None:
        for server in self._servers:
            await server.aclose()

    async def list_tools(self, operator_token: str | None = None) -> list[ToolDescriptor]:
        """Every tool every configured server publishes right now.

        Asked of all of them at once — one slow server would otherwise make the model
        wait for it before the turn could start, and the whole point of asking before the
        first model call is that the set is fixed for the turn.
        """
        configured = [server for server in self._servers if server.configured]
        if not configured:
            return []

        answers = await asyncio.gather(
            *(server.list_tools(operator_token) for server in configured)
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

    async def call(
        self, name: str, arguments: dict, operator_token: str | None = None
    ) -> ToolOutcome:
        """Dispatch to the server that announced this name.

        A name nobody announced is an outcome rather than an exception, like every other
        failure on this seam: the model asked for something that is not there, and the
        turn continues with that as its answer.
        """
        server = self._owner.get(name)
        if server is None:
            return ToolOutcome(
                ToolOutcomeKind.UNAVAILABLE,
                f"no configured tool server announces {name!r}, so this call was not made",
                0,
            )
        return await server.call(name, arguments, operator_token)
