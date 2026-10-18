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
