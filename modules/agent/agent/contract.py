"""The shapes this module answers with — snake_case on the wire, same convention as
`market_data/contract.py`. Not generated: this module's contract is hand-written on both
sides rather than wired into `pnpm contract:generate`, which is market-data's alone
(design.md, "Kontrakt terminala pisany ręcznie, bez generatora").
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, field_validator, model_validator

from .models import Message, Session, UsageAggregate
from .models_catalogue import ModelCatalogueEntry

# A name the operator types, not one derived from the first question — so it may be longer
# than `store.derive_title`'s 60, but not unbounded: the conversation list is a narrow
# column that truncates, and a title past this is one nothing can show.
TITLE_MAX_CHARS = 120


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


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    model_id: str | None
    prompt_version: str | None
    incomplete: bool
    created_at: datetime

    @classmethod
    def from_message(cls, message: Message) -> MessageOut:
        return cls(
            id=message.id,
            role=message.role.value,
            content=message.content,
            model_id=message.model_id,
            prompt_version=message.prompt_version,
            incomplete=message.incomplete,
            created_at=message.created_at,
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


class SendMessageIn(BaseModel):
    content: str


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
