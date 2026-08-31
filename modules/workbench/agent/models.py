"""What this module stores, as it sees it — mirrors `market_data/models.py`'s split:
pydantic shapes here, the queries that fill them in `store.py`."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Literal

from pydantic import BaseModel


class Role(str, Enum):
    OPERATOR = "operator"
    AGENT = "agent"


class Session(BaseModel):
    id: int
    owner_principal: str
    # `None` until the first exchange — specs/agent-chat, "Pusta sesja nie zaśmieca
    # historii": a session without a title has not earned a place on the list yet.
    title: str | None
    current_model_id: str
    created_at: datetime
    last_active_at: datetime


class Message(BaseModel):
    id: int
    session_id: int
    role: Role
    content: str
    # Set on an agent message only — which model and which system prompt produced it.
    model_id: str | None
    prompt_version: str | None
    incomplete: bool
    # Why it is incomplete, when it is: the operator said stop. A reply that broke is something to try
    # again, and one that was stopped is something somebody meant.
    stopped: bool
    created_at: datetime


class Usage(BaseModel):
    id: int
    session_id: int
    message_id: int
    model_id: str
    # `None`, not zero, when the provider reported nothing for this call.
    input_tokens: int | None
    output_tokens: int | None
    cached_tokens: int | None
    reasoning_tokens: int | None
    input_rate_per_1m: Decimal
    output_rate_per_1m: Decimal
    cost: Decimal | None
    created_at: datetime


class RecordedCall(BaseModel):
    """A tool call that happened, before it has a row. Built by the graph — the only place that knows which
    round it belonged to — and handed to the store once the agent message it belongs to exists."""

    round_index: int
    name: str
    arguments: dict
    outcome: str
    text: str
    duration_ms: int
    # Set only for a call that could change the account: its row was written before the call was sent, so
    # this one already exists and is only joined to the reply.
    row_id: int | None = None


class ToolCall(BaseModel):
    """One call the agent made while producing an agent message — not a `Message`, on purpose: the transcript is the
    conversation. `message_id` is `None` for a call that outlived its turn, written before being sent and never answered."""

    id: int
    session_id: int
    message_id: int | None
    round_index: int
    position: int
    tool_name: str
    arguments: dict
    outcome: str
    result_text: str
    duration_ms: int
    created_at: datetime


class ChartIndicator(BaseModel):
    """One indicator instance as the agent asked for it — the terminal's own selection shape minus the
    instance key. `params` empty means "whatever the catalogue defaults to"."""

    id: str
    params: dict[str, float] = {}
    color: str | None = None


class ChartSnapshot(BaseModel):
    """What the consumer says it is drawing at the moment it asks a question. Not stored and not a message:
    it describes the instant the question was asked, not a state this module keeps."""

    symbol: str | None = None
    resolution: str | None = None
    indicators: list[ChartIndicator] = []
    # The visible span, each half optional on its own: a consumer that draws but cannot say what is on
    # screen still sends the rest.
    visible_from: datetime | None = None
    visible_to: datetime | None = None

    def as_context(self) -> str:
        """One line for the system prompt. Written for a model to read, so it names the
        parameters rather than listing ids the model would have to look up."""
        drawn = ", ".join(
            indicator.id
            + (
                "("
                + ", ".join(f"{name}={value:g}" for name, value in sorted(indicator.params.items()))
                + ")"
                if indicator.params
                else ""
            )
            for indicator in self.indicators
        )
        parts = [
            f"symbol {self.symbol}" if self.symbol else "no symbol",
            f"interval {self.resolution}" if self.resolution else "no interval",
            f"indicators {drawn}" if drawn else "no indicators",
        ]
        sentence = "The operator's chart currently shows: " + "; ".join(parts) + "."
        if self.visible_from is not None and self.visible_to is not None:
            sentence += (
                f" The visible time span runs from {self.visible_from.isoformat()} "
                f"to {self.visible_to.isoformat()}."
            )
        return sentence


class ChartFocus(BaseModel):
    """Which fragment of the time axis the chart should show — exactly one of its three shapes filled. Absolute time on
    the wire, so a command sitting in the log for an hour still means what it meant; `last_bars` is the one exception."""

    # No wire alias here — this shape is only ever read back by this module's own store. The "from" alias
    # a caller sends and sees lives on `ChartFocusOut`, where the wire is what matters.
    from_: datetime | None = None
    to: datetime | None = None
    around: datetime | None = None
    bars: int | None = None
    last_bars: int | None = None


class ChartCommand(BaseModel):
    """What the agent set the chart to, once, declaratively: `None` means "leave that as it is", never "clear it", and an
    empty `indicators` list is the one way to say "draw none". `sequence` rises across the module, not per session."""

    sequence: int
    session_id: int
    symbol: str | None
    resolution: str | None
    indicators: list[ChartIndicator] | None
    focus: ChartFocus | None
    created_at: datetime

    def merged_with(self, later: ChartCommand) -> ChartCommand:
        """This command, then a newer one on top — the later value wins per field, and a field the later
        one left alone keeps this one's. What makes it safe for a consumer to skip what it missed."""
        return ChartCommand(
            sequence=later.sequence,
            session_id=later.session_id,
            symbol=later.symbol if later.symbol is not None else self.symbol,
            resolution=later.resolution if later.resolution is not None else self.resolution,
            indicators=later.indicators if later.indicators is not None else self.indicators,
            focus=later.focus if later.focus is not None else self.focus,
            created_at=later.created_at,
        )


class ChartLevel(BaseModel):
    """A single price, optionally in effect only from a moment on. `kind` is what the store's four-column
    geometry discriminates on; `at` fills `time_a`, `price` fills `price_a`, and the rest stay null."""

    kind: Literal["level"] = "level"
    price: float
    at: datetime | None = None
    label: str | None = None
    color: str | None = None


class ChartZone(BaseModel):
    """A price band, optionally bounded in time. `bottom` fills `price_a`, `top` fills `price_b` and must
    exceed it — checked here for an early refusal, and by the database regardless."""

    kind: Literal["zone"] = "zone"
    top: float
    bottom: float
    from_: datetime | None = None
    to: datetime | None = None
    label: str | None = None
    color: str | None = None


class ChartTrendlinePoint(BaseModel):
    time: datetime
    price: float


class ChartTrendline(BaseModel):
    """Two points, `a` and `b` — never `from`/`to`, which `ChartZone` already uses for a pair of moments
    alone; a trend line's pair is a moment *and* a price each."""

    kind: Literal["trendline"] = "trendline"
    a: ChartTrendlinePoint
    b: ChartTrendlinePoint
    label: str | None = None
    color: str | None = None


# What `draw_on_chart`'s `add` carries in, and what `store.add_drawings` takes — the
# shape alone, without the identity the database hands out on insert.
ChartDrawingGeometry = ChartLevel | ChartZone | ChartTrendline


class ChartDrawing(BaseModel):
    """One drawing as stored: `geometry`'s own `kind` says which of the three shapes it is. `session_id`
    is nullable — a drawing outlives the session that made it."""

    id: int
    symbol: str
    session_id: int | None
    geometry: ChartDrawingGeometry
    # Whether the chart draws it. Beside `created_at` rather than inside `geometry`: `label` and `color`
    # say how the drawing looks, this says whether it is drawn at all.
    hidden: bool
    created_at: datetime
    updated_at: datetime


class PromptRevision(BaseModel):
    """One saved system prompt, both variants together — "two texts, one version", a row instead of a
    constant. Never updated after insert; the current one is whichever has the highest `id`."""

    version: str
    with_tools_body: str
    without_tools_body: str
    created_at: datetime
    # Where the row came from: a deployment's migration, or a person. Not on the wire — it exists so the
    # module can refuse to let a seed cover an operator's save.
    source: Literal["seed", "operator"] = "operator"


class UsageAggregate(BaseModel):
    """One row of a `GROUP BY` over `usage`. Sums ignore the rows they cannot price, and `unknown_count`
    is how many of those a caller silently dropping them would hide."""

    key: str
    input_tokens: int
    output_tokens: int
    cost: Decimal
    unknown_count: int
