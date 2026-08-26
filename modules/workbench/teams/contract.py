"""The shapes this module answers with, snake_case and with no separate domain layer, its tables mapping onto the wire
almost one to one. `TeamDefinition` is the exception: the *pure* shape is checked here, the rest at save time."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from croniter import croniter
from pydantic import BaseModel, Field, ValidationInfo, field_validator, model_validator

from .config import ModelCatalogueEntry
from .recurrence import Recurrence, from_cron, to_cron


def _parse_jsonb(value: object) -> Any:
    # asyncpg hands JSONB back as text unless a codec is registered — same reading
    # agent's own store gives its JSONB columns.
    return json.loads(value) if isinstance(value, str) else value


# What a team may remember, in three numbers — constants rather than settings, on `docs/architecture.md`'s split: these
# bound the shape in which this module hands anything to a model, so an env var must not move them.
MEMORY_ENTRY_MAX_CHARS = 2000
MEMORY_READ_LIMIT = 20
MEMORY_WRITES_PER_RUN = 10


class ModelOut(BaseModel):
    """One entry of the model catalogue — everything a picker needs and nothing else. The terminal MUST NOT
    carry a model id of its own, so a model added to configuration reaches the picker with no change there."""

    id: str
    display_name: str
    cost_rank: int
    # Per 1,000,000 tokens, the unit providers quote, published in the unit it is configured in. Strings
    # for the same reason every cost on this wire is one.
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


class ToolOut(BaseModel):
    """One tool as the server announces it right now — name and description, deliberately not the input schema, which
    would put a copy of somebody else's contract on this wire. `read_only` travels; `None` means unknown, not read-only."""

    name: str
    description: str
    read_only: bool | None = None


class AgentDefinition(BaseModel):
    """One role inside a team: what it is told, which model answers for it, and which
    tools it may reach for."""

    # Stable within one revision — what edges point at and what `run_steps.agent_key`
    # records, so it MUST NOT be a display label a later revision is free to rename.
    key: str
    role: str
    prompt: str
    # "Wytyczne" — operational instructions beyond the system prompt (tone, what never
    # to do). Optional: a team's first draft may have none.
    guidance: str = ""
    model_id: str
    tools: list[str] = Field(default_factory=list)

    @field_validator("key", "role", "prompt", "model_id")
    @classmethod
    def _not_blank(cls, value: str, info: ValidationInfo) -> str:
        if not value.strip():
            raise ValueError(f"agent {info.field_name} must not be blank")
        return value.strip()

    @field_validator("tools")
    @classmethod
    def _tools_are_unique_and_named(cls, value: list[str]) -> list[str]:
        cleaned = [tool.strip() for tool in value]
        if any(not tool for tool in cleaned):
            raise ValueError("a tool name must not be blank")
        if len(cleaned) != len(set(cleaned)):
            raise ValueError(f"agent carries the same tool twice: {cleaned}")
        return cleaned


class TeamEdge(BaseModel):
    """One dependency: `to` waits for `from_` and receives its output — specs/teams-runs,
    'Agent widzi wypowiedzi poprzedników, a nie całą historię przebiegu'."""

    # Two one-way aliases for one wire name: `from` is a Python keyword, and a type checker rejects
    # `TeamEdge(from_=...)` if `alias=` were used instead of the pair below.
    from_: str = Field(validation_alias="from", serialization_alias="from")
    to: str

    model_config = {"populate_by_name": True}


class CostLimits(BaseModel):
    """Budgets a revision may carry. Strings, like every other cost on this wire: nothing here computes
    with these, only compares them, and a string round-trips exactly where a float invites rescaling."""

    run_limit: str | None = Field(default=None, description="max cost for one run")
    daily_limit: str | None = Field(default=None, description="max cost per day for this team")

    @field_validator("run_limit", "daily_limit")
    @classmethod
    def _positive_decimal(cls, value: str | None, info: ValidationInfo) -> str | None:
        if value is None:
            return None
        try:
            parsed = Decimal(value)
        except InvalidOperation as err:
            raise ValueError(f"{info.field_name} is not a number: {value!r}") from err
        if parsed <= 0:
            raise ValueError(f"{info.field_name} must be positive, got {value}")
        return str(parsed)


class TradingLimits(BaseModel):
    """What a revision allows its agents to do to the account: all three optional, an omitted one meaning no limit at
    all. What is not negotiable lives a module away, in a `trading-mcp` that starts only against the demo account."""

    max_order_size: str | None = Field(
        default=None, description="largest size one order may carry; null means no limit"
    )
    orders_per_run: int | None = Field(
        default=None, description="how many orders one run may place; null means no limit"
    )
    orders_per_day: int | None = Field(
        default=None,
        description="how many orders this team may place per UTC day; null means no limit",
    )

    @field_validator("max_order_size")
    @classmethod
    def _positive_decimal(cls, value: str | None, info: ValidationInfo) -> str | None:
        if value is None:
            return None
        try:
            parsed = Decimal(value)
        except InvalidOperation as err:
            raise ValueError(f"{info.field_name} is not a number: {value!r}") from err
        if parsed <= 0:
            raise ValueError(f"{info.field_name} must be positive, got {value}")
        return str(parsed)

    @field_validator("orders_per_run", "orders_per_day")
    @classmethod
    def _positive_count(cls, value: int | None, info: ValidationInfo) -> int | None:
        # Zero is refused rather than read as "none allowed": a team that may place no orders is one
        # whose agents should carry no write tools, and the two are different statements.
        if value is not None and value <= 0:
            raise ValueError(f"{info.field_name} must be positive, got {value}")
        return value


class TeamDefinition(BaseModel):
    """The whole of what a team revision carries, as one immutable blob. `trading` defaults to an empty `TradingLimits`,
    which is what every revision saved before that field existed reads back as, and it means the same thing: no limit."""

    agents: list[AgentDefinition]
    edges: list[TeamEdge] = Field(default_factory=list)
    limits: CostLimits = Field(default_factory=CostLimits)
    trading: TradingLimits = Field(default_factory=TradingLimits)

    @model_validator(mode="before")
    @classmethod
    def _every_agent_names_a_model(cls, data: Any) -> Any:
        """Before the agents parse, so the refusal can name the agent by its own `key`. Pydantic would
        refuse this on its own — as `agents.2.model_id`, which leaves the operator counting rows."""
        if not isinstance(data, dict):
            return data
        agents = data.get("agents")
        if not isinstance(agents, list):
            return data
        for index, agent in enumerate(agents):
            if not isinstance(agent, dict):
                continue
            model_id = agent.get("model_id")
            if isinstance(model_id, str) and model_id.strip():
                continue
            named = agent.get("key") if isinstance(agent.get("key"), str) else index
            raise ValueError(
                f"agent {named!r} names no model — every agent in a team names its own "
                "(there is no team-wide default)"
            )
        return data

    @field_validator("agents")
    @classmethod
    def _at_least_one_agent_with_unique_keys(
        cls, value: list[AgentDefinition]
    ) -> list[AgentDefinition]:
        if not value:
            raise ValueError("a team needs at least one agent")
        keys = [agent.key for agent in value]
        if len(keys) != len(set(keys)):
            raise ValueError(f"duplicate agent keys: {keys}")
        return value

    @model_validator(mode="after")
    def _edges_name_real_agents(self) -> TeamDefinition:
        keys = {agent.key for agent in self.agents}
        for edge in self.edges:
            if edge.from_ not in keys:
                raise ValueError(f"edge names unknown agent {edge.from_!r} as its source")
            if edge.to not in keys:
                raise ValueError(f"edge names unknown agent {edge.to!r} as its target")
            if edge.from_ == edge.to:
                raise ValueError(f"agent {edge.from_!r} depends on itself")
        pairs = [(edge.from_, edge.to) for edge in self.edges]
        if len(pairs) != len(set(pairs)):
            raise ValueError("the same dependency is named more than once")
        return self

    @model_validator(mode="after")
    def _no_isolated_agent_among_connected_ones(self) -> TeamDefinition:
        # A team with no edges at all is fine: every agent works independently, by choice. An agent
        # touching none while others are wired together is not a choice, it is a forgotten edge.
        if not self.edges:
            return self
        touched = {edge.from_ for edge in self.edges} | {edge.to for edge in self.edges}
        isolated = sorted(agent.key for agent in self.agents if agent.key not in touched)
        if isolated:
            raise ValueError(f"agent(s) with no dependency in either direction: {isolated}")
        return self

    @model_validator(mode="after")
    def _no_dependency_cycle(self) -> TeamDefinition:
        forward: dict[str, list[str]] = {agent.key: [] for agent in self.agents}
        incoming: dict[str, int] = {agent.key: 0 for agent in self.agents}
        for edge in self.edges:
            forward[edge.from_].append(edge.to)
            incoming[edge.to] += 1

        # Kahn's algorithm: repeatedly remove nodes with no remaining incoming edge. A
        # node still left once nothing more can be removed sits on a cycle.
        remaining = dict(incoming)
        frontier = [key for key, count in remaining.items() if count == 0]
        resolved = 0
        while frontier:
            node = frontier.pop()
            resolved += 1
            for target in forward[node]:
                remaining[target] -= 1
                if remaining[target] == 0:
                    frontier.append(target)
        if resolved != len(self.agents):
            cyclic = sorted(key for key, count in remaining.items() if count > 0)
            raise ValueError(f"dependency cycle involving: {cyclic}")
        return self


class CreateTeamIn(BaseModel):
    name: str
    description: str = ""
    definition: TeamDefinition

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, value: str) -> str:
        collapsed = " ".join(value.split())
        if not collapsed:
            raise ValueError("name is blank — a team needs one to appear in the catalogue")
        return collapsed


class SaveRevisionIn(BaseModel):
    definition: TeamDefinition


class AgentPlace(BaseModel):
    """One agent's place on the canvas. Its own shape rather than a field on `AgentDefinition`: a
    coordinate inside an immutable definition would mint a revision every time a node was dragged."""

    agent_key: str
    x: float
    y: float


class TeamLayoutOut(BaseModel):
    """Where the operator left each agent. Absent keys are not an error and not a zero: the canvas computes
    a place from the dependencies for anything this does not name."""

    places: list[AgentPlace]

    @classmethod
    def from_rows(cls, rows: Iterable[Mapping[str, Any]]) -> TeamLayoutOut:
        return cls(
            places=[
                AgentPlace(agent_key=row["agent_key"], x=row["x"], y=row["y"]) for row in rows
            ]
        )


class SaveLayoutIn(BaseModel):
    """The whole layout at once, replacing what was stored. A patch per node would need
    the module to know which agents still exist, and the canvas already does."""

    places: list[AgentPlace]

    @field_validator("places")
    @classmethod
    def _keys_are_distinct(cls, value: list[AgentPlace]) -> list[AgentPlace]:
        keys = [place.agent_key for place in value]
        if len(set(keys)) != len(keys):
            raise ValueError("the same agent is placed twice")
        return value


class TeamOut(BaseModel):
    """A row in the catalogue. No `owner_principal` on the wire: ownership gates which rows a query returns
    at all, the same way agent's own `SessionOut` never carries one."""

    id: int
    name: str
    description: str
    latest_revision: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> TeamOut:
        return cls(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            latest_revision=row["latest_revision"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


class TeamRevisionOut(BaseModel):
    id: int
    team_id: int
    version: int
    definition: TeamDefinition
    created_at: datetime

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> TeamRevisionOut:
        return cls(
            id=row["id"],
            team_id=row["team_id"],
            version=row["version"],
            definition=TeamDefinition.model_validate(_parse_jsonb(row["definition"])),
            created_at=row["created_at"],
        )


class RunOut(BaseModel):
    id: int
    team_revision_id: int
    # pending, running, completed, failed, or cancelled — kept as a plain string the way agent's own
    # `ToolCallOut.outcome` is, with the CHECK constraint as the actual enforcement.
    status: str
    stopped_reason: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> RunOut:
        return cls(
            id=row["id"],
            team_revision_id=row["team_revision_id"],
            status=row["status"],
            stopped_reason=row["stopped_reason"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            created_at=row["created_at"],
        )


class RunStepOut(BaseModel):
    id: int
    run_id: int
    agent_key: str
    # pending, running, completed, or failed — `run_steps.status`.
    status: str
    output: str | None
    rounds: int
    started_at: datetime | None
    finished_at: datetime | None

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> RunStepOut:
        return cls(
            id=row["id"],
            run_id=row["run_id"],
            agent_key=row["agent_key"],
            status=row["status"],
            output=row["output"],
            rounds=row["rounds"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
        )


class ToolCallOut(BaseModel):
    id: int
    run_step_id: int
    round_index: int
    position: int
    tool_name: str
    arguments: dict
    # ok, refused, or unavailable — `tool_calls.outcome`.
    outcome: str
    result_text: str
    duration_ms: int
    created_at: datetime

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> ToolCallOut:
        return cls(
            id=row["id"],
            run_step_id=row["run_step_id"],
            round_index=row["round_index"],
            position=row["position"],
            tool_name=row["tool_name"],
            arguments=_parse_jsonb(row["arguments"]),
            outcome=row["outcome"],
            result_text=row["result_text"],
            duration_ms=row["duration_ms"],
            created_at=row["created_at"],
        )


class MemoryEntryOut(BaseModel):
    """One thing a team decided to keep. `author_agent_key` and `run_id` are legibility, not permission,
    and `run_id` is optional because an entry outlives the run that wrote it."""

    id: int
    author_agent_key: str
    run_id: int | None
    content: str
    created_at: datetime

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> MemoryEntryOut:
        return cls(
            id=row["id"],
            author_agent_key=row["author_agent_key"],
            run_id=row["run_id"],
            content=row["content"],
            created_at=row["created_at"],
        )


class TeamMemoryOut(BaseModel):
    """What a team remembers, newest first — and how much of it there is. `total` rides beside the entries
    because the read is cut at a ceiling, and a cut nobody can see is a memory the reader believes complete."""

    entries: list[MemoryEntryOut]
    total: int

    @classmethod
    def from_rows(cls, rows: Iterable[Mapping[str, Any]], *, total: int) -> TeamMemoryOut:
        return cls(entries=[MemoryEntryOut.from_row(row) for row in rows], total=total)


class TradeOut(BaseModel):
    """One call a run made that could change the account, read as a *trade*, as columns rather than JSON. A row still
    saying `sent` after its run finished is an order whose fate this module does not know."""

    id: int
    run_id: int
    run_step_id: int
    agent_key: str
    tool_name: str
    symbol: str | None
    direction: str | None
    size: str | None
    level: str | None
    status: str
    result_status: str | None
    provider_order_id: str | None
    reference: str | None
    created_at: datetime
    settled_at: datetime | None

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> TradeOut:
        size = row["size"]
        level = row["level"]
        return cls(
            id=row["id"],
            run_id=row["run_id"],
            run_step_id=row["run_step_id"],
            agent_key=row["agent_key"],
            tool_name=row["tool_name"],
            symbol=row["symbol"],
            direction=row["direction"],
            size=None if size is None else str(size),
            level=None if level is None else str(level),
            status=row["status"],
            result_status=row["result_status"],
            provider_order_id=row["provider_order_id"],
            reference=row["reference"],
            created_at=row["created_at"],
            settled_at=row["settled_at"],
        )


class UsageOut(BaseModel):
    id: int
    run_id: int
    run_step_id: int
    model_id: str
    input_tokens: int | None
    output_tokens: int | None
    cached_tokens: int | None
    reasoning_tokens: int | None
    # A string, like every other cost/rate on this contract — see `CostLimits`. NULL
    # exactly when the tokens it would be computed from are (specs/teams-usage).
    cost: str | None
    created_at: datetime

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> UsageOut:
        cost = row["cost"]
        return cls(
            id=row["id"],
            run_id=row["run_id"],
            run_step_id=row["run_step_id"],
            model_id=row["model_id"],
            input_tokens=row["input_tokens"],
            output_tokens=row["output_tokens"],
            cached_tokens=row["cached_tokens"],
            reasoning_tokens=row["reasoning_tokens"],
            cost=None if cost is None else str(cost),
            created_at=row["created_at"],
        )


class UsageAggregateOut(BaseModel):
    key: str
    input_tokens: int
    output_tokens: int
    cost: str
    unknown_count: int


class UsageSummaryOut(BaseModel):
    """`by_agent` is the read the requirement is for; `by_model` is agent's own precedent, kept because a
    run can genuinely mix cheap and expensive models across agents."""

    total_cost: str
    by_agent: list[UsageAggregateOut]
    by_model: list[UsageAggregateOut]


# Phase 3 — a team running without an operator at the keyboard. `ScheduleIn` and `TriggerIn` carry the same
# revision-selection shape and are validated the same way rather than sharing a base class for two fields.


def _revision_selection_is_coherent(revision_mode: str, pinned_revision_id: int | None) -> None:
    """`pinned` names a revision, `latest` names none, and nothing else is well-formed."""
    if revision_mode == "pinned" and pinned_revision_id is None:
        raise ValueError("revision_mode 'pinned' needs pinned_revision_id")
    if revision_mode == "latest" and pinned_revision_id is not None:
        raise ValueError("revision_mode 'latest' must not carry pinned_revision_id")


class ScheduleTiming(BaseModel):
    """When a schedule fires, said either way — as a rhythm, or as the cron expression the clock runs. Exactly one of
    the two, shared by the save and the preview, so a draft cannot preview happily and then fail on save."""

    cron_expression: str | None = None
    recurrence: Recurrence | None = None

    @field_validator("cron_expression")
    @classmethod
    def _cron_is_well_formed(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not croniter.is_valid(stripped):
            raise ValueError(f"{stripped!r} is not a valid five-field cron expression")
        return stripped

    @model_validator(mode="after")
    def _one_way_of_saying_it(self) -> ScheduleTiming:
        if (self.cron_expression is None) == (self.recurrence is None):
            raise ValueError("name the schedule's timing either by recurrence or by cron_expression")
        return self

    def cron(self) -> str:
        """The expression this timing runs as — the translation lives in `recurrence.py`,
        and this is the only place a route asks for it."""
        if self.cron_expression is not None:
            return self.cron_expression
        assert self.recurrence is not None  # enforced by `_one_way_of_saying_it`
        return to_cron(self.recurrence)


class ScheduleIn(ScheduleTiming):
    """What an operator submits to create or edit a schedule."""

    revision_mode: Literal["pinned", "latest"] = "pinned"
    pinned_revision_id: int | None = None

    @model_validator(mode="after")
    def _revision_selection(self) -> ScheduleIn:
        _revision_selection_is_coherent(self.revision_mode, self.pinned_revision_id)
        return self


class NextFiresIn(ScheduleTiming):
    """A timing the operator has not saved — what the preview asks about."""

    count: int = 5


class ScheduleOut(BaseModel):
    id: int
    team_id: int
    revision_mode: str
    pinned_revision_id: int | None
    cron_expression: str
    # The same expression as a rhythm, or `None` when it is not one of them — read back here rather than
    # stored, so an operator who wrote their own expression gets it back unchanged.
    recurrence: Recurrence | None
    # Set at creation and after every claim — never read by a caller to decide anything, only shown; the
    # module is the one clock.
    next_fire_at: datetime
    enabled: bool
    disabled_reason: str | None
    consecutive_failures: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> ScheduleOut:
        return cls(
            id=row["id"],
            team_id=row["team_id"],
            revision_mode=row["revision_mode"],
            pinned_revision_id=row["pinned_revision_id"],
            cron_expression=row["cron_expression"],
            recurrence=from_cron(row["cron_expression"]),
            next_fire_at=row["next_fire_at"],
            enabled=row["enabled"],
            disabled_reason=row["disabled_reason"],
            consecutive_failures=row["consecutive_failures"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


class NextFiresOut(BaseModel):
    """The module's own answer to "when does this schedule fire next", computed fresh from the expression
    rather than read off `next_fire_at` — which reflects the last claim and goes stale once disabled."""

    times: list[datetime]


class TriggerIn(BaseModel):
    """A market condition, expressed as a call to a tool this module already has a session for — never a
    locally computed indicator. `threshold` is a string for the reason every unrescalable number here is."""

    revision_mode: Literal["pinned", "latest"] = "pinned"
    pinned_revision_id: int | None = None
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    field_path: str
    comparison: Literal["gt", "gte", "lt", "lte", "eq"]
    threshold: str
    cooldown_seconds: int = 900
    poll_interval_seconds: int = 300

    @field_validator("tool_name", "field_path")
    @classmethod
    def _not_blank(cls, value: str, info: ValidationInfo) -> str:
        if not value.strip():
            raise ValueError(f"{info.field_name} must not be blank")
        return value.strip()

    @field_validator("threshold")
    @classmethod
    def _threshold_is_a_number(cls, value: str) -> str:
        try:
            parsed = Decimal(value)
        except InvalidOperation as err:
            raise ValueError(f"threshold is not a number: {value!r}") from err
        return str(parsed)

    @field_validator("cooldown_seconds", "poll_interval_seconds")
    @classmethod
    def _positive(cls, value: int, info: ValidationInfo) -> int:
        if value <= 0:
            raise ValueError(f"{info.field_name} must be positive, got {value}")
        return value

    @model_validator(mode="after")
    def _revision_selection(self) -> TriggerIn:
        _revision_selection_is_coherent(self.revision_mode, self.pinned_revision_id)
        return self


class TriggerOut(BaseModel):
    id: int
    team_id: int
    revision_mode: str
    pinned_revision_id: int | None
    tool_name: str
    arguments: dict[str, Any]
    field_path: str
    comparison: str
    threshold: str
    cooldown_seconds: int
    poll_interval_seconds: int
    next_check_at: datetime
    # `None` until the first check ever runs, and `None` again whenever the tool server could not be asked
    # — a third value, not a `false`.
    last_result: bool | None
    last_checked_at: datetime | None
    last_fired_at: datetime | None
    enabled: bool
    disabled_reason: str | None
    consecutive_failures: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> TriggerOut:
        return cls(
            id=row["id"],
            team_id=row["team_id"],
            revision_mode=row["revision_mode"],
            pinned_revision_id=row["pinned_revision_id"],
            tool_name=row["tool_name"],
            arguments=_parse_jsonb(row["arguments"]),
            field_path=row["field_path"],
            comparison=row["comparison"],
            threshold=str(row["threshold"]),
            cooldown_seconds=row["cooldown_seconds"],
            poll_interval_seconds=row["poll_interval_seconds"],
            next_check_at=row["next_check_at"],
            last_result=row["last_result"],
            last_checked_at=row["last_checked_at"],
            last_fired_at=row["last_fired_at"],
            enabled=row["enabled"],
            disabled_reason=row["disabled_reason"],
            consecutive_failures=row["consecutive_failures"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


class ScheduleFireOut(BaseModel):
    """One fire attempt from either source, including one that started nothing. Exactly one of
    `schedule_id`/`trigger_id` is set, mirroring the row's own CHECK constraint."""

    id: int
    schedule_id: int | None
    trigger_id: int | None
    fired_at: datetime
    outcome: str
    reason: str | None
    run_id: int | None
    skipped_count: int

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> ScheduleFireOut:
        return cls(
            id=row["id"],
            schedule_id=row["schedule_id"],
            trigger_id=row["trigger_id"],
            fired_at=row["fired_at"],
            outcome=row["outcome"],
            reason=row["reason"],
            run_id=row["run_id"],
            skipped_count=row["skipped_count"],
        )
