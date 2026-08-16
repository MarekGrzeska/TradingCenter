"""The shapes this module answers with — snake_case on the wire, same convention as
`market_data/contract.py`. Not generated: this module's contract is hand-written on both
sides rather than wired into `pnpm contract:generate`, which is market-data's alone
(design.md, "Kontrakt terminala pisany ręcznie, bez generatora").
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from pydantic import BaseModel, Field, ValidationInfo, field_validator, model_validator

from .models import (
    ChartCommand,
    ChartFocus,
    ChartIndicator,
    ChartSnapshot,
    Message,
    PromptRevision,
    RecordedCall,
    Session,
    ToolCall,
    UsageAggregate,
)
from .models_catalogue import ModelCatalogueEntry
from .tools.chart import CHART_TOOL_NAME
from .tools.drawings import DRAW_TOOL_NAME, LIST_DRAWINGS_TOOL_NAME

# A name the operator types, not one derived from the first question — so it may be longer
# than `store.derive_title`'s 60, but not unbounded: the conversation list is a narrow
# column that truncates, and a title past this is one nothing can show.
TITLE_MAX_CHARS = 120

# Tools this module runs itself. Imported rather than spelled again: a tool's name is
# decided where the tool is written.
MODULE_TOOL_NAMES = frozenset({CHART_TOOL_NAME, DRAW_TOOL_NAME, LIST_DRAWINGS_TOOL_NAME})


class ModelOut(BaseModel):
    id: str
    display_name: str
    cost_rank: int
    # Per 1,000,000 tokens, the unit providers quote — published in the same unit it is
    # configured in, so the terminal renders the string as it arrives and never rescales
    # it. Strings, not numbers: a rate like 0.2 round-trips exactly as text, and nothing
    # here ever sums these on the wire — the terminal reads them to render, never to
    # compute (design.md, "terminal niczego nie przelicza").
    input_rate_per_1m: str
    output_rate_per_1m: str

    @classmethod
    def from_entry(cls, entry: ModelCatalogueEntry) -> ModelOut:
        return cls(
            id=entry.id,
            display_name=entry.display_name,
            cost_rank=entry.cost_rank,
            input_rate_per_1m=str(entry.input_rate_per_1m),
            output_rate_per_1m=str(entry.output_rate_per_1m),
        )


class SessionOut(BaseModel):
    id: int
    title: str | None
    current_model_id: str
    created_at: datetime
    last_active_at: datetime

    @classmethod
    def from_session(cls, session: Session) -> SessionOut:
        return cls(
            id=session.id,
            title=session.title,
            current_model_id=session.current_model_id,
            created_at=session.created_at,
            last_active_at=session.last_active_at,
        )


def _source_of(tool_name: str) -> str:
    return "module" if tool_name in MODULE_TOOL_NAMES else "server"


class ToolCallOut(BaseModel):
    """One tool call, published in exactly one shape whether it is leaving as a stream
    event mid-turn or hanging off a message in a reloaded transcript. Both are built here
    on purpose: two shapes for the same call is two chances for the panel and the
    transcript to disagree about what the agent asked and what came back.

    No `id` and no `created_at`: the live event has neither — the row does not exist yet
    when the call resolves — and a field one of the two paths cannot fill is a field the
    reader has to check the origin of before trusting.
    """

    # Which round of the turn, and where within it. The transcript arrives ordered
    # already; these say whether three calls were one round of three or three rounds of
    # one, which is the difference between a model surveying and a model iterating.
    round_index: int
    position: int
    tool_name: str
    arguments: dict
    # ok, refused, or unavailable — `ToolOutcomeKind` in `tools/client.py`, and the three
    # never collapse into two (specs/agent-tools, "Odmowa narzędzia jest wynikiem, nie
    # awarią tury").
    outcome: str
    # The text the model itself received, not a summary of it. A caller shown a summary
    # cannot tell that the model was handed something else, which is the whole reason
    # this is published (design.md, "Wynik w całości, bez własnego sufitu").
    result_text: str
    duration_ms: int
    # Who ran it: the tool server, or this module itself. Derived from the name rather
    # than stored, so there is one list of the module's own tools and no column that can
    # disagree with it (specs/agent-tools, "Narzędzie własne modułu obok narzędzi
    # serwera").
    source: str = Field(examples=["server", "module"])

    @classmethod
    def from_tool_call(cls, call: ToolCall) -> ToolCallOut:
        return cls(
            round_index=call.round_index,
            position=call.position,
            tool_name=call.tool_name,
            arguments=call.arguments,
            outcome=call.outcome,
            result_text=call.result_text,
            duration_ms=call.duration_ms,
            source=_source_of(call.tool_name),
        )

    @classmethod
    def from_recorded(cls, call: RecordedCall, position: int) -> ToolCallOut:
        return cls(
            round_index=call.round_index,
            position=position,
            tool_name=call.name,
            arguments=call.arguments,
            outcome=call.outcome,
            result_text=call.text,
            duration_ms=call.duration_ms,
            source=_source_of(call.name),
        )


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    model_id: str | None
    prompt_version: str | None
    incomplete: bool
    created_at: datetime
    # Empty for an operator's message and for an agent message that asked nothing — never
    # absent, and never null. "No calls" and "the calls were lost on the way" are two
    # different facts, and a field that is sometimes missing collapses them
    # (specs/agent-tools, "Wypowiedź bez narzędzi").
    tool_calls: list[ToolCallOut] = Field(default_factory=list)

    @classmethod
    def from_message(cls, message: Message, tool_calls: Sequence[ToolCall] = ()) -> MessageOut:
        return cls(
            id=message.id,
            role=message.role.value,
            content=message.content,
            model_id=message.model_id,
            prompt_version=message.prompt_version,
            incomplete=message.incomplete,
            created_at=message.created_at,
            tool_calls=[ToolCallOut.from_tool_call(call) for call in tool_calls],
        )


class CreateSessionIn(BaseModel):
    # Absent or null both mean "no preference" — the route resolves it to the module's
    # default, the same as specs/agent-models requires when a session is created with
    # no model named at all.
    model_id: str | None = None


class PatchSessionIn(BaseModel):
    """Both fields optional, at least one required — one route for two edits that an
    operator makes at different moments and never together: the model changes mid-thought,
    the name once the rozmowa turned out to be about something worth finding again."""

    model_id: str | None = None
    title: str | None = None

    @field_validator("title")
    @classmethod
    def _title_is_a_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        collapsed = " ".join(value.split())
        if not collapsed:
            raise ValueError(
                "title is blank — a session with no name would drop off the list "
                "entirely, which is not what renaming asks for. Delete it instead."
            )
        if len(collapsed) > TITLE_MAX_CHARS:
            raise ValueError(f"title is longer than {TITLE_MAX_CHARS} characters")
        return collapsed

    @model_validator(mode="after")
    def _asks_for_something(self) -> PatchSessionIn:
        if self.model_id is None and self.title is None:
            raise ValueError("neither model_id nor title given — this request changes nothing")
        return self


class ChartIndicatorIn(BaseModel):
    id: str
    params: dict[str, float] = Field(default_factory=dict)
    color: str | None = None


class ChartSnapshotIn(BaseModel):
    """What the caller is drawing right now. Optional everywhere: a consumer without a
    chart — every one except the terminal — has nothing to send, and a turn without this
    behaves exactly as it did before the field existed."""

    symbol: str | None = None
    resolution: str | None = None
    indicators: list[ChartIndicatorIn] = Field(default_factory=list)
    visible_from: datetime | None = None
    visible_to: datetime | None = None

    def to_snapshot(self) -> ChartSnapshot:
        return ChartSnapshot(
            symbol=self.symbol,
            resolution=self.resolution,
            indicators=[
                ChartIndicator(id=i.id, params=i.params, color=i.color) for i in self.indicators
            ],
            visible_from=self.visible_from,
            visible_to=self.visible_to,
        )


class SendMessageIn(BaseModel):
    content: str
    chart: ChartSnapshotIn | None = Field(
        default=None,
        description="what the caller is drawing as it asks; given to the model as context "
        "for this turn only, never written to the transcript",
    )


class ChartIndicatorOut(BaseModel):
    id: str
    params: dict[str, float]
    color: str | None


class ChartFocusOut(BaseModel):
    from_: datetime | None = Field(default=None, serialization_alias="from")
    to: datetime | None = None
    around: datetime | None = None
    bars: int | None = None
    last_bars: int | None = None

    @classmethod
    def from_focus(cls, focus: ChartFocus) -> ChartFocusOut:
        return cls(
            from_=focus.from_,
            to=focus.to,
            around=focus.around,
            bars=focus.bars,
            last_bars=focus.last_bars,
        )


class ChartCommandOut(BaseModel):
    """What the chart should show now, and the sequence number that says so.

    Several commands the consumer missed arrive folded into one — `sequence` is the
    newest of them, and a field left null by every one of them is still null here,
    meaning "leave it as it is" (specs/agent-chart-control, "Konsument czyta tylko to,
    czego jeszcze nie zastosował")."""

    sequence: int
    symbol: str | None
    resolution: str | None
    indicators: list[ChartIndicatorOut] | None
    focus: ChartFocusOut | None
    created_at: datetime

    @classmethod
    def from_command(cls, command: ChartCommand) -> ChartCommandOut:
        return cls(
            sequence=command.sequence,
            symbol=command.symbol,
            resolution=command.resolution,
            indicators=None
            if command.indicators is None
            else [
                ChartIndicatorOut(id=i.id, params=i.params, color=i.color)
                for i in command.indicators
            ],
            focus=None if command.focus is None else ChartFocusOut.from_focus(command.focus),
            created_at=command.created_at,
        )


class UsageAggregateOut(BaseModel):
    key: str
    input_tokens: int
    output_tokens: int
    # A string, like every other cost/rate on this contract — see ModelOut.
    cost: str
    unknown_count: int

    @classmethod
    def from_aggregate(cls, aggregate: UsageAggregate) -> UsageAggregateOut:
        return cls(
            key=aggregate.key,
            input_tokens=aggregate.input_tokens,
            output_tokens=aggregate.output_tokens,
            cost=str(aggregate.cost),
            unknown_count=aggregate.unknown_count,
        )


class UsageSummaryOut(BaseModel):
    total_cost: str
    by_model: list[UsageAggregateOut]
    by_session: list[UsageAggregateOut]
    by_day: list[UsageAggregateOut]


class PromptOut(BaseModel):
    version: str
    with_tools: str
    without_tools: str
    updated_at: datetime

    @classmethod
    def from_revision(cls, revision: PromptRevision) -> PromptOut:
        return cls(
            version=revision.version,
            with_tools=revision.with_tools_body,
            without_tools=revision.without_tools_body,
            updated_at=revision.created_at,
        )


class PromptUpdateIn(BaseModel):
    with_tools: str
    without_tools: str

    @field_validator("with_tools", "without_tools")
    @classmethod
    def _not_blank(cls, value: str, info: ValidationInfo) -> str:
        if not value.strip():
            raise ValueError(
                f"{info.field_name} is blank — an agent needs a system prompt to run with."
            )
        return value
