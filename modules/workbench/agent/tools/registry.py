"""Every source of tools this surface knows about, behind one door — a drop-in for a single `ToolServer`. Independence
is the property worth stating: one unreachable source costs the model its tools and nothing else."""

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
        """The network servers, plus whatever the assembly hands in. `local_sources` defaults to none, so
        this class stays buildable from settings, which is all it can know by itself."""
        return cls(
            [
                ToolServer(settings, prefix="market_mcp"),
                # The one whose writes land on the account. No operator identity: the account is one and
                # shared, and trading-mcp reads no such header.
                ToolServer(settings, prefix="trading_mcp", can_move_the_account=True),
                # No polymarket and no social server: both archives are packages of this process since
                # `one-process-per-security-boundary`, and their tools arrive through `local_sources`.
                # The door to Telegram. Its send tool is the only thing on any of these surfaces whose
                # effect is visible outside this system — and it moves no account, so not that flag.
                ToolServer(settings, prefix="telegram_mcp"),
                # The strategy platform: what it decided and how many setups it stands on. Every tool
                # there carries readOnlyHint, and the module has no route to an account to move.
                ToolServer(settings, prefix="strategy_mcp"),
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
        """Every tool every configured source publishes right now, asked of all of them at once — one slow
        server would otherwise make the model wait before the turn could start."""
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
        """Whether this name belongs to a tool that could change the account, answered from the descriptors
        `list_tools` already read. A name nobody announced is not account-moving."""
        server = self._owner.get(name)
        return server is not None and server.moves_the_account(name)

    async def call(
        self, name: str, arguments: dict, operator_principal: str | None = None
    ) -> ToolOutcome:
        """Dispatch to the source that announced this name. A name nobody announced is an outcome rather
        than an exception, like every other failure on this seam."""
        server = self._owner.get(name)
        if server is None:
            return ToolOutcome(
                ToolOutcomeKind.UNAVAILABLE,
                f"no configured tool source announces {name!r}, so this call was not made",
                0,
            )
        return await server.call(name, arguments, operator_principal)
