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
    created_at: datetime


class Usage(BaseModel):
    id: int
    session_id: int
    message_id: int
    model_id: str
    # `None`, not zero, when the provider reported nothing for this call
    # (specs/agent-usage, "Zużycia, którego dostawca nie podał, MUST NOT być
    # zgadywane").
    input_tokens: int | None
    output_tokens: int | None
    cached_tokens: int | None
    reasoning_tokens: int | None
    input_rate_per_1m: Decimal
    output_rate_per_1m: Decimal
    cost: Decimal | None
    created_at: datetime


class RecordedCall(BaseModel):
    """A tool call that happened, before it has a row. Built by the graph — the only
    place that knows which round it belonged to and what it cost in time — and handed to
    `store.record_tool_calls` once the agent message it belongs to exists."""

    round_index: int
    name: str
    arguments: dict
    outcome: str
    text: str
    duration_ms: int
    # Set only for a call that could change the account: its row was written before the
    # call was sent, so this one already exists and is not to be inserted again — only
    # joined to the reply (specs/agent-trading). `None` is every other call, and the
    # sentence above it describes those.
    row_id: int | None = None


class ToolCall(BaseModel):
    """One call the agent made while producing an agent message.

    Not a `Message`, on purpose: the transcript is the conversation, and this is how the
    agent got to its half of it (specs/agent-tools, "Wywołanie narzędzia zostawia ślad").

    `outcome` distinguishes four answers that must never be collapsed into fewer — see
    `ToolOutcomeKind` in `tools/client.py`, which is where they are decided.

    `message_id` is `None` for a call that outlived its turn: it was written before being
    sent, and the reply it would have hung off never came (specs/agent-trading).
    """

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
    """One indicator instance as the agent asked for it — the terminal's own selection
    shape minus the instance key, which the terminal hands out itself when it applies
    this. `params` empty means "whatever the catalogue defaults to"."""

    id: str
    params: dict[str, float] = {}
    color: str | None = None


class ChartSnapshot(BaseModel):
    """What the consumer says it is drawing at the moment it asks a question. Not stored
    and not a message: it describes the instant the question was asked, not a state this
    module keeps (specs/agent-chat, "Tura wie, co terminal właśnie rysuje")."""

    symbol: str | None = None
    resolution: str | None = None
    indicators: list[ChartIndicator] = []
    # The visible span, each half optional on its own: a consumer that draws but cannot
    # say what is on screen still sends the rest (specs/agent-chat, "Tura wie, co terminal
    # właśnie rysuje").
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
    """Which fragment of the time axis the chart should show. Exactly one of the three
    shapes this carries MUST be filled: `from_`/`to` (a range), `around`/`bars` (a point
    and a span around it), or `last_bars` (the newest N candles) — checked by the tool
    that builds this, not here (specs/agent-chart-control, "Narzędzie ustawia zawartość
    aktywnego slotu").

    Absolute time on the wire, not relative to the moment the command is read: a command
    sitting in the log for an hour must mean the same thing it meant when it was issued.
    `last_bars` is the one named exception — it means "the end of the series", whatever
    that is at the moment it is applied.
    """

    # No wire alias here — this shape is only ever read back by this module's own store,
    # never by another module. The "from" alias a caller actually sends and sees lives on
    # `ChartFocusOut` and the tool's own parsing, where the wire is what matters.
    from_: datetime | None = None
    to: datetime | None = None
    around: datetime | None = None
    bars: int | None = None
    last_bars: int | None = None


class ChartCommand(BaseModel):
    """What the agent set the chart to, once. Declarative: `None` on a field means "leave
    that as it is", never "clear it" — a model asked to add an average must not be able
    to blank the symbol by omission (specs/agent-chart-control, "Narzędzie ustawia
    zawartość aktywnego slotu"). An empty `indicators` list is the one way to say "draw
    none", and it is a list, not a None. A missing `focus` means "leave the operator
    looking where they are".

    `sequence` is the row's own id: rising across the whole module, not per session, so a
    consumer holding one number knows what it has already applied.
    """

    sequence: int
    session_id: int
    symbol: str | None
    resolution: str | None
    indicators: list[ChartIndicator] | None
    focus: ChartFocus | None
    created_at: datetime

    def merged_with(self, later: ChartCommand) -> ChartCommand:
        """This command, then a newer one on top — the later value wins per field, and a
        field the later one left alone keeps this one's.

        What makes it safe for a consumer to skip the commands it missed while it was
        away: one merged answer says what the chart should look like now, where replaying
        only the newest would silently drop an earlier command's indicators."""
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
    """A single price, optionally in effect only from a moment on — support, resistance,
    a level the operator or the agent wants to keep looking at. `kind` is what the
    store's four-column geometry (`design.md`, "Zapis: cztery kolumny geometrii i CHECK
    per kształt") discriminates on; `at` fills `time_a`, `price` fills `price_a`, and
    `time_b`/`price_b` stay null — the shape the database's own `chart_drawings_level_
    shape` check enforces independently of this class ever agreeing."""

    kind: Literal["level"] = "level"
    price: float
    at: datetime | None = None
    label: str | None = None
    color: str | None = None


class ChartZone(BaseModel):
    """A price band, optionally bounded in time. `bottom` fills `price_a`, `top` fills
    `price_b` and must exceed it — checked here for an early refusal, and by
    `chart_drawings_zone_shape` regardless."""

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
    """Two points, `a` and `b` — never `from`/`to`, which `ChartZone` already uses for a
    pair of moments alone; a trend line's pair is a moment *and* a price each. `a.time`
    fills `time_a`, `b.time` fills `time_b` and must be later."""

    kind: Literal["trendline"] = "trendline"
    a: ChartTrendlinePoint
    b: ChartTrendlinePoint
    label: str | None = None
    color: str | None = None


# What `draw_on_chart`'s `add` carries in, and what `store.add_drawings` takes — the
# shape alone, without the identity the database hands out on insert.
ChartDrawingGeometry = ChartLevel | ChartZone | ChartTrendline


class ChartDrawing(BaseModel):
    """One drawing as stored: `geometry`'s own `kind` says which of the three shapes it
    is, and carries that shape's fields plus the label and colour every shape takes the
    same way (specs/agent-chart-drawings, "Rysunek należy do instrumentu, nie do
    widoku"). `session_id` is nullable — a drawing outlives the session that made it."""

    id: int
    symbol: str
    session_id: int | None
    geometry: ChartDrawingGeometry
    # Whether the chart draws it. Beside `created_at` rather than inside `geometry` on
    # purpose: `label` and `color` say how the drawing looks, this says whether it is
    # drawn at all, and at a change of shape it would have nowhere to go
    # (specs/agent-chart-drawings, "Rysunki są trwałe i mają własną tożsamość").
    hidden: bool
    created_at: datetime
    updated_at: datetime


class PromptRevision(BaseModel):
    """One saved system prompt, both variants together — "two texts, one version",
    the same shape `PROMPT_VERSION` always was, now a row instead of a constant
    (specs/agent-prompt-management, "Zapis tworzy nową wersję, nigdy nie nadpisuje
    istniejącej"). Never updated after insert; the current one is whichever has the
    highest `id`."""

    version: str
    with_tools_body: str
    without_tools_body: str
    created_at: datetime
    # Where the row came from: a deployment's migration, or a person. Not on the wire —
    # it exists so the module can refuse to let a seed cover an operator's save
    # (specs/agent-prompt-management, "Zasiew z wdrożenia nie przykrywa tego, co
    # zapisał operator"), not so anybody reads it.
    source: Literal["seed", "operator"] = "operator"


class UsageAggregate(BaseModel):
    """One row of a `GROUP BY` over `usage` — by model, by session, or by day,
    depending which query built it. Sums ignore the rows they cannot price;
    `unknown_count` is how many of those a caller silently dropping them would hide
    (specs/agent-usage, "Zużycie da się odczytać zbiorczo")."""

    key: str
    input_tokens: int
    output_tokens: int
    cost: Decimal
    unknown_count: int
