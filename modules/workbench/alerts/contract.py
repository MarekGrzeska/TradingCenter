"""The wire shapes of the REST contract. A rule is written and read in the same shape, so the terminal's form and its
list are one type; a refusal names the fields at fault, so the form can put each reason beside its field."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, field_validator

Comparison = Literal["gt", "gte", "lt", "lte", "eq"]
FilterOp = Literal["eq", "ne", "in", "gt", "gte", "lt", "lte", "contains"]
Mode = Literal["once", "repeat"]


class Defect(BaseModel):
    """One thing wrong with a rule, and the field it is wrong in (a dotted path into the rule as written)."""

    field: str
    message: str


class Problem(BaseModel):
    """One refusal shape for every route. `defects` is filled when a rule was refused for what it says."""

    detail: str
    defects: list[Defect] = Field(default_factory=list)


class FilterTerm(BaseModel):
    """One comparison of an event's attribute with a value. A rule's filter is all of its terms at once."""

    attribute: str
    op: FilterOp
    value: bool | float | str | list[str]


class ConditionSource(BaseModel):
    """A value the tool surface can be asked for, compared with a number. `threshold` is a string for the reason every
    unrescalable number here is."""

    kind: Literal["condition"] = "condition"
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    field_path: str
    comparison: Comparison
    threshold: str
    poll_interval_seconds: int = 60

    @field_validator("tool_name", "field_path")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value.strip()

    @field_validator("threshold")
    @classmethod
    def _is_a_number(cls, value: str) -> str:
        try:
            return str(Decimal(value))
        except InvalidOperation as err:
            raise ValueError(f"not a number: {value!r}") from err


class EventSource(BaseModel):
    """Something another package announced, narrowed by its attributes."""

    kind: Literal["event"] = "event"
    event_type: str
    filter: list[FilterTerm] = Field(default_factory=list)

    @field_validator("event_type")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value.strip()


Source = Annotated[ConditionSource | EventSource, Field(discriminator="kind")]


class RuleIn(BaseModel):
    """What the operator submits to create a rule or replace one. Empty `template` and a missing `cooldown_seconds` take
    the default of the rule's kind, which is why they are not required."""

    name: str = Field(min_length=1, max_length=80)
    source: Source
    destination: str = Field(min_length=1)
    template: str = ""
    cooldown_seconds: int | None = Field(default=None, ge=0)
    mode: Mode = "repeat"
    max_per_hour: int | None = Field(default=None, ge=1)
    enabled: bool = True

    @field_validator("name", "destination")
    @classmethod
    def _stripped(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped


class DraftIn(BaseModel):
    sentence: str = Field(min_length=3, max_length=1000)


class DraftOut(BaseModel):
    """A proposal. `rule` is what the form is filled with, `defects` is everything wrong with it as it stands — the
    sentence's own problems and the same refusals a saved rule would meet — and nothing is stored."""

    understood: str
    rule: RuleIn | None
    defects: list[Defect]
    notes: list[str]


class RulePatch(BaseModel):
    enabled: bool


class RuleOut(BaseModel):
    id: int
    name: str
    source: Source
    destination: str
    template: str
    cooldown_seconds: int
    mode: Mode
    max_per_hour: int | None
    enabled: bool
    disabled_reason: str | None
    # What is wrong with the rule now, and was not when it was written: the recipient is gone, or a new schema took the
    # attribute it filters on. Empty is a rule that can work.
    defects: list[Defect]
    created_by: str
    created_at: datetime
    updated_at: datetime
    # `None` until the first look, and `None` again whenever the value could not be had — a third value, not a `false`.
    last_result: bool | None
    last_checked_at: datetime | None
    last_fired_at: datetime | None
    next_check_at: datetime | None


class ToolOut(BaseModel):
    name: str
    description: str
    source: str = Field(description="which package's tool surface offers it")
    arguments: dict[str, Any] = Field(description="the tool's input schema, as the tool publishes it")
    number_fields: list[str] = Field(
        description="the paths into its answer that hold a number — the only ones a rule can compare"
    )


class EventTypeIn(BaseModel):
    description: str = Field(min_length=1)
    schema_: dict[str, Any] = Field(alias="schema", description="JSON Schema of the attributes an event of this type carries")

    model_config = {"populate_by_name": True}


class EventTypeOut(BaseModel):
    name: str
    description: str
    schema_: dict[str, Any] = Field(alias="schema")
    announced_by: str | None
    last_announced_at: datetime
    # The values a text attribute has had in the events kept — only for the attributes whose schema asks for it
    # (`"x-seen-values": true`), which are the ones with a handful of values worth choosing between.
    seen: dict[str, list[str]] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}


class EventIn(BaseModel):
    """Something that happened, as the package it happened in reports it. `source_key` is the producer's own name for this
    occurrence (a film's id, a post's id): the same key published twice is one event, so a producer may retry until it hears yes."""

    type: str = Field(min_length=1)
    source_key: str = Field(min_length=1, max_length=200)
    attributes: dict[str, Any] = Field(default_factory=dict)
    # The message the producer would send on its own, ready — what a rule that writes no template of its own says.
    text: str = Field(min_length=1, max_length=4000)


class EventAccepted(BaseModel):
    id: int
    # `True` when this occurrence had been published before; nothing new was decided about it.
    duplicate: bool
    # How many rules went off because of it.
    fires: int


class FireOut(BaseModel):
    at: datetime
    state: Literal["pending", "delivered", "refused", "abandoned", "throttled", "undeliverable"]
    reason: str | None
    text: str


class CheckOut(BaseModel):
    at: datetime
    outcome: Literal["unavailable", "refused", "cooldown"]
    reason: str


class HistoryOut(BaseModel):
    """What became of a rule lately, newest first: every time it went off and whether the message arrived, and every time it
    could not look at its value or crossed its level inside the cool-down."""

    fires: list[FireOut]
    checks: list[CheckOut]


class ClockOut(BaseModel):
    ran: bool
    age_seconds: float = Field(description="since the clock last finished a tick, or since it started if it has not")
    expected_seconds: float


class StateOut(BaseModel):
    """What the package cannot say through a list of rules: whether it is doing its job at all."""

    rules_enabled: int
    rules_disabled: int
    # Rules quiet for a reason that is not the market's: a recipient who is gone, a schema that took an attribute away.
    rules_with_defects: int
    # Fires that have not arrived yet and are still being tried.
    waiting_fires: int
    event_types: int
    # `False` when the process has no door to Telegram: rules are checked and fire, and nothing reaches a phone.
    delivering: bool
    # `False` without ALERTS_OPENAI_API_KEY.
    drafting: bool
    # `False` when the process hands this package no tools: value rules cannot be looked at.
    reading_values: bool
    clock: ClockOut


class DestinationOut(BaseModel):
    name: str
    bot: str
    receives: bool


class CatalogOut(BaseModel):
    """Everything a rule can be made of, in one read: the form is built from this and nothing is typed from memory."""

    tools: list[ToolOut]
    event_types: list[EventTypeOut]
    destinations: list[DestinationOut]
    # `False` when the process has no door to Telegram: rules can be written, and nothing is delivered.
    gateway: bool
    min_interval_seconds: int
    # The pairs the archive follows, for the instrument field; empty where the archive cannot be asked.
    symbols: list[str]
    # `False` without ALERTS_OPENAI_API_KEY: the sentence box says why it is switched off.
    drafting: bool
