"""What this module stores, as it sees it — mirrors `market_data/models.py`'s split:
pydantic shapes here, the queries that fill them in `store.py`."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum

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


class ToolCall(BaseModel):
    """One call the agent made while producing an agent message.

    Not a `Message`, on purpose: the transcript is the conversation, and this is how the
    agent got to its half of it (specs/agent-tools, "Wywołanie narzędzia zostawia ślad").

    `outcome` distinguishes three answers that must never be collapsed into two — see
    `ToolOutcomeKind` in `tools/client.py`, which is where they are decided.
    """

    id: int
    session_id: int
    message_id: int
    round_index: int
    position: int
    tool_name: str
    arguments: dict
    outcome: str
    result_text: str
    duration_ms: int
    created_at: datetime


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
