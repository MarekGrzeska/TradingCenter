"""Neutral, provider-agnostic DTOs — the module's real contract.

capital.com is mapped into these; callers never see a raw provider payload. There is
deliberately no ``BrokerPort`` beside them: a Protocol is structural, so it constrains
nothing unless something is annotated with it, and these models are what the HTTP
contract is actually made of.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator


class AssetClass(str, Enum):
    SHARES = "SHARES"
    INDICES = "INDICES"
    CRYPTO = "CRYPTO"
    CURRENCIES = "CURRENCIES"
    COMMODITIES = "COMMODITIES"
    OTHER = "OTHER"


class Direction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class Resolution(str, Enum):
    """Candle time frame. One vocabulary serves REST and streaming alike —
    ``GET /prices/{epic}?resolution=`` and ``OHLCMarketData.subscribe`` take the
    same spellings."""

    MINUTE = "MINUTE"
    MINUTE_5 = "MINUTE_5"
    MINUTE_15 = "MINUTE_15"
    MINUTE_30 = "MINUTE_30"
    HOUR = "HOUR"
    HOUR_4 = "HOUR_4"
    DAY = "DAY"
    WEEK = "WEEK"


class OrderStatus(str, Enum):
    FILLED = "FILLED"  # market order executed
    WORKING = "WORKING"  # accepted but resting (pending limit/stop)
    CLOSED = "CLOSED"  # a position close settled
    CANCELLED = "CANCELLED"  # a working order cancellation settled
    UPDATED = "UPDATED"  # a position amendment (SL/TP) settled
    REJECTED = "REJECTED"
    PENDING = "PENDING"  # not yet settled — the confirmation is still in flight


class OrderType(str, Enum):
    MARKET = "MARKET"  # immediate -> POST /positions
    LIMIT = "LIMIT"  # resting, below/above market -> POST /workingorders
    STOP = "STOP"  # resting stop -> POST /workingorders


class Instrument(BaseModel):
    symbol: str
    name: str
    asset_class: AssetClass
    tradeable: bool
    bid: float | None = None
    ask: float | None = None
    lot_size: float | None = None
    provider: str = "capital.com"


class InstrumentPage(BaseModel):
    """Result of enumerating instruments — carries the truncation signal, so a partial
    catalogue is never mistaken for a complete one."""

    instruments: list[Instrument]
    count: int
    truncated: bool
    nodes_visited: int


class Candle(BaseModel):
    """One candle, built from the **bid** side. The stream uses the same side, which is
    what lets history and live data be joined without a step at the seam."""

    ts: str
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: float | None = None
    resolution: Resolution
    # True while the period this candle covers has not finished. The provider serves
    # candles up to the present, so a read reaching now hands back the period it is in —
    # complete in every field and still going to change. A consumer that cannot tell will
    # store a price from halfway through a period as the period's result, and nothing
    # downstream ever looks wrong enough to catch it.
    forming: bool = False


class CandleHistory(BaseModel):
    """A deep read, with what it cost.

    The provider serves at most 1000 candles per request, so a deep read is many
    requests and can take tens of seconds. ``requests`` makes that visible instead of
    leaving a caller to guess why a read was slow, and ``history_ended`` distinguishes
    "the instrument has no more data" from "we stopped early" — both of which otherwise
    look identical: a series shorter than the one asked for.
    """

    candles: list[Candle]
    count: int
    requested: int
    requests: int
    resolution: Resolution
    first_ts: str | None = None
    last_ts: str | None = None
    history_ended: bool = False


class Account(BaseModel):
    id: str
    name: str
    currency: str
    balance: float
    available: float
    pnl: float
    active: bool = False


class Position(BaseModel):
    id: str
    symbol: str
    direction: Direction
    size: float
    open_level: float | None = None
    pnl: float | None = None
    currency: str | None = None


class Order(BaseModel):
    status: OrderStatus
    id: str | None = None
    reference: str | None = None
    symbol: str | None = None
    direction: Direction | None = None
    size: float | None = None
    level: float | None = None
    reason: str | None = None


class WorkingOrder(BaseModel):
    id: str
    symbol: str
    direction: Direction
    size: float
    order_type: OrderType
    level: float | None = None
    good_till: str | None = None
    currency: str | None = None


class PlaceOrderRequest(BaseModel):
    symbol: str = Field(examples=["GOLD"])
    direction: Direction = Field(examples=[Direction.BUY])
    size: float = Field(examples=[0.01], gt=0)
    order_type: OrderType = OrderType.MARKET
    level: float | None = Field(default=None, description="target price — required for LIMIT/STOP")
    good_till: str | None = Field(default=None, description="ISO time-in-force for pending orders")
    stop_loss: float | None = Field(default=None, description="attached stop-loss level")
    take_profit: float | None = Field(default=None, description="attached take-profit level")
    provider_params: dict = Field(
        default_factory=dict,
        description="Escape hatch: provider-specific order params forwarded verbatim.",
    )

    @model_validator(mode="after")
    def _level_required_for_pending(self) -> PlaceOrderRequest:
        if self.order_type in (OrderType.LIMIT, OrderType.STOP) and self.level is None:
            raise ValueError(f"{self.order_type.value} order requires a 'level'")
        return self


class UpdatePositionRequest(BaseModel):
    """Amend an open position's stops. Tri-state per field: omitted leaves it unchanged,
    a number sets that level, ``null`` removes it."""

    stop_loss: float | None = None
    take_profit: float | None = None

    @model_validator(mode="after")
    def _not_empty(self) -> UpdatePositionRequest:
        if not self.model_fields_set:
            raise ValueError(
                "provide stop_loss and/or take_profit (a number to set, null to remove)"
            )
        return self


class Capabilities(BaseModel):
    provider: str
    environment: str
    has_positions: bool
    has_streaming: bool
    has_working_orders: bool
    order_types: list[str]
