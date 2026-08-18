"""A tool server announcing one write tool and answering without a session.

Shared by the two files that need a run to place a real order — the trace tests and the
route tests. The session itself is `test_tool_server.py`'s subject; what matters here is
the pair the runner reads a call as an order from: `read_only=False` on the tool, and
`can_move_the_account` on the server it came from (specs/trading-mcp-tools, "Narzędzie
zapisujące jest oznaczone jako zmieniające stan"). Both, because the tool's annotation
alone says nothing about whether it can reach an account.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

from teams.provider import ProviderChunk, TextDelta, ToolCallRequest, UsageReport
from teams.tools import ToolDescriptor, ToolOutcome, ToolOutcomeKind, ToolServer

from .mcp_stand_in import settings_for
from .scripted_provider import Ask

FILLED = json.dumps(
    {
        "outcome": "settled",
        "status": "FILLED",
        "id": "deal-1",
        "reference": "ref-1",
        "symbol": "GOLD",
        "direction": "BUY",
        "size": 1.0,
        "level": 2400.0,
    }
)


class WriteServer(ToolServer):
    def __init__(self, reply: str = FILLED, kind: ToolOutcomeKind = ToolOutcomeKind.OK) -> None:
        super().__init__(settings_for(None), can_move_the_account=True)
        self._reply = reply
        self._kind = kind
        self.calls = 0

    @property
    def configured(self) -> bool:
        # The base class reads this off MARKET_MCP_URL, which this stub has none of — it
        # answers directly instead of opening a session.
        return True

    async def list_tools(self) -> list[ToolDescriptor]:
        return [
            ToolDescriptor(
                name="place_order",
                description="places an order",
                input_schema={},
                read_only=False,
            ),
            ToolDescriptor(
                name="get_positions",
                description="reads positions",
                input_schema={},
                read_only=True,
            ),
        ]

    async def call(self, name: str, arguments: dict) -> ToolOutcome:
        del name, arguments
        self.calls += 1
        return ToolOutcome(self._kind, self._reply, 5)


def places_orders(count: int, arguments: dict | None = None):
    """A model that asks to place an order `count` times, then answers."""
    order = arguments or {"symbol": "GOLD", "direction": "BUY", "size": 1}

    def script(ask: Ask) -> Sequence[ProviderChunk]:
        if ask.rounds < count:
            return [
                ToolCallRequest(id=f"call-{ask.rounds}", name="place_order", arguments=order),
                UsageReport(10, 2, None, None),
            ]
        return [TextDelta("done"), UsageReport(10, 2, None, None)]

    return script
