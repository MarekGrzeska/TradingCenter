"""Data as a builder, so a test says only what it is about. The tools are the shapes the real archives publish, written by
hand: a test of this package does not import its neighbours."""

from __future__ import annotations

from typing import Any

from alerts.catalog import CatalogTool, ToolOutcome
from alerts.contract import ConditionSource, EventSource, FilterTerm, RuleIn
from alerts.gateway import Recipient
from alerts.validation import Known

LAST_PRICE_INPUT = {
    "type": "object",
    "properties": {
        "symbol": {"type": "string"},
        "resolution": {"anyOf": [{"type": "string"}, {"type": "null"}], "default": None},
    },
    "required": ["symbol"],
}
LAST_PRICE_OUTPUT = {
    "type": "object",
    "properties": {
        "symbol": {"type": "string"},
        "close": {"anyOf": [{"type": "number"}, {"type": "null"}], "default": None},
        "age_seconds": {"anyOf": [{"type": "number"}, {"type": "null"}], "default": None},
        "forming": {"type": "boolean", "default": False},
    },
    "required": ["symbol"],
}
FILM_SCHEMA = {
    "type": "object",
    "properties": {
        "channel": {"type": "string"},
        "impact_score": {"type": "integer"},
        "instruments": {"type": "array", "items": {"type": "string"}},
        "forming": {"type": "boolean"},
        "text": {"type": "string"},
    },
}


def tool(
    name: str = "get_last_price",
    *,
    read_only: bool | None = True,
    input_schema: dict[str, Any] | None = None,
    output_schema: dict[str, Any] | None = None,
    source: str = "market-data",
) -> CatalogTool:
    return CatalogTool(
        name=name,
        description=f"{name} for a test",
        source=source,
        input_schema=LAST_PRICE_INPUT if input_schema is None else input_schema,
        output_schema=LAST_PRICE_OUTPUT if output_schema is None else output_schema,
        read_only=read_only,
    )


def known(
    *,
    tools: list[CatalogTool] | None = None,
    event_types: dict[str, dict[str, Any]] | None = None,
    destinations: frozenset[str] | None = frozenset({"phone"}),
    min_interval_seconds: int = 30,
) -> Known:
    return Known(
        tools={one.name: one for one in (tools if tools is not None else [tool(), tool("add_channel", read_only=False)])},
        event_types={"youtube.film.read": FILM_SCHEMA} if event_types is None else event_types,
        destinations=destinations,
        min_interval_seconds=min_interval_seconds,
    )


def condition(**overrides: Any) -> ConditionSource:
    values: dict[str, Any] = {
        "tool_name": "get_last_price",
        "arguments": {"symbol": "EURUSD"},
        "field_path": "close",
        "comparison": "gt",
        "threshold": "1.10",
        "poll_interval_seconds": 60,
    }
    return ConditionSource(**{**values, **overrides})


def event(terms: list[FilterTerm] | None = None, **overrides: Any) -> EventSource:
    return EventSource(**{"event_type": "youtube.film.read", "filter": terms or [], **overrides})


def rule(source: ConditionSource | EventSource | None = None, **overrides: Any) -> RuleIn:
    values: dict[str, Any] = {"name": "a rule", "source": source or condition(), "destination": "phone"}
    return RuleIn(**{**values, **overrides})


class FakeTools:
    """The tool surface of a process, with a price that can be moved."""

    def __init__(self, tools: list[CatalogTool] | None = None) -> None:
        self._tools = tools if tools is not None else [tool(), tool("add_channel", read_only=False)]
        self.price = 1.05

    async def tools(self) -> list[CatalogTool]:
        return self._tools

    async def call(self, name: str, arguments: dict[str, Any]) -> ToolOutcome:
        return ToolOutcome("ok", f'{{"symbol": "{arguments.get("symbol")}", "close": {self.price}}}')


class FakeGateway:
    """The door's list of recipients, which can fail."""

    def __init__(self, names: list[str] | None = None) -> None:
        self.names = ["phone"] if names is None else names
        self.down = False

    async def recipients(self) -> list[Recipient]:
        from alerts.gateway import GatewayUnreachable

        if self.down:
            raise GatewayUnreachable("the door to Telegram did not answer: test")
        return [Recipient(name, "@bot", True) for name in self.names]
