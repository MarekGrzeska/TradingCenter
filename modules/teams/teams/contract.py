"""The shapes this module answers with — snake_case on the wire, same convention as
`market_data/contract.py` and `agent/contract.py`.

No separate domain-model layer the way `agent/models.py` is one: agent's contract diverges
from storage (a computed `source` field, geometry unions), which is what a dataclass in
between is for. This module's simple tables map onto their wire shape almost one to one, so
each `*Out` reads an `asyncpg.Record` directly through its own `from_row` — a parallel
dataclass with the same fields and no behaviour of its own would be duplication, not
architecture.

`TeamDefinition` is the one exception and the one shape that matters most: it is both what
gets stored in `team_revisions.definition` (JSONB) and what the wire carries, unchanged
either way, because there is nothing about a definition that storage needs and a caller
should not see. What is validated here is the *pure* shape — unique agent keys, edges naming
real agents, no isolated agent, no dependency cycle — because none of it needs anything
outside this JSON. Whether a `model_id` is in the module's configured catalogue or a tool
name is one market-mcp still announces needs a database and a live session neither Pydantic
nor this file has, so those two checks are the store's job at the moment a revision is
actually saved (specs/teams-catalogue, "Definicja, której nie da się wykonać, jest
odrzucana przy zapisie").
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from croniter import croniter
from pydantic import BaseModel, Field, ValidationInfo, field_validator, model_validator

from .config import ModelCatalogueEntry


def _parse_jsonb(value: object) -> Any:
    # asyncpg hands JSONB back as text unless a codec is registered — same reading
    # agent's own store.py gives its JSONB columns.
    return json.loads(value) if isinstance(value, str) else value


class ModelOut(BaseModel):
    """One entry of the model catalogue — everything a picker needs and nothing else
    (specs/teams-models, "Katalog modeli wystarcza do zbudowania wybieraka"). The
    terminal MUST NOT carry a model id of its own, so a model added to this module's
    configuration reaches the picker with no terminal change at all."""

    id: str
    display_name: str
    cost_rank: int
    # Per 1,000,000 tokens, the unit providers quote — published in the unit it is
    # configured in, so the terminal renders what arrives and never rescales it. Strings
    # for the same reason every cost on this wire is one (see `CostLimits`).
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
    """One tool as the tool server announces it right now (specs/teams-tool-access,
    "Moduł nie trzyma kopii tego, co ogłasza serwer narzędzi").

    Name and description, and deliberately not the input schema: a definition points at a
    tool by name and carries nothing else about it, so the picker needs a label and a line
    of prose. Publishing the schema would put a copy of somebody else's contract on this
    module's wire, where it would be stale from the first argument market-mcp renames.
    """

    name: str
    description: str


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

    # Two one-way aliases for one wire name — see market_data's `Uncovered.from_` for
    # why: `from` is a Python keyword, and building this model with a type checker
    # rejects `TeamEdge(from_=...)` if `alias=` were used instead of the pair below.
    from_: str = Field(validation_alias="from", serialization_alias="from")
    to: str

    model_config = {"populate_by_name": True}


class CostLimits(BaseModel):
    """Budgets a revision may carry — specs/teams-usage, 'Przekroczenie granicy kosztu
    zatrzymuje przebieg'. Strings, like every other cost on this contract's wire: nothing
    here computes with these, only compares them against a running total, and a string
    round-trips exactly where a float would invite rescaling it should never do."""

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


class TeamDefinition(BaseModel):
    """The whole of what a team revision carries — every agent, every dependency between
    them, and the cost limits a run against this revision must respect. One immutable
    blob per revision (specs/teams-catalogue, "Rewizja raz zapisana się nie zmienia")."""

    agents: list[AgentDefinition]
    edges: list[TeamEdge] = Field(default_factory=list)
    limits: CostLimits = Field(default_factory=CostLimits)

    @model_validator(mode="before")
    @classmethod
    def _every_agent_names_a_model(cls, data: Any) -> Any:
        """Before the agents parse, so the refusal can name the agent by its own `key`.

        `model_id` is a required field, so Pydantic would refuse this on its own — but as
        `agents.2.model_id`, which leaves the operator counting rows in a canvas to find
        out which role it means (specs/teams-models, "Agent bez wskazanego modelu": the
        refusal names *that agent*).
        """
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
        # specs/teams-catalogue, "Agent, do którego nic nie prowadzi i który do niczego
        # nie prowadzi": a team with no edges at all is fine — every agent works
        # independently, by choice. An agent touching none while others ARE wired
        # together is not a choice; it is the edge someone forgot to draw.
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


class TeamOut(BaseModel):
    """A row in the catalogue — specs/teams-catalogue, "Katalog wystarcza, żeby wybrać
    zespół bez otwierania go". No `owner_principal` on the wire: ownership gates which
    rows a query returns at all (specs/teams-browser-access), the same way agent's own
    `SessionOut` never carries one either."""

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
    # pending, running, completed, failed, or cancelled — `runs.status` in the schema;
    # kept as a plain string here the way agent's own `ToolCallOut.outcome` is, with the
    # CHECK constraint as the actual enforcement.
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
    """specs/teams-usage, "Odczyt zużycia w rozbiciu na role" — `by_agent` is the read
    that requirement is for; `by_model` is agent's own `UsageSummaryOut` precedent,
    kept because a run can genuinely mix cheap and expensive models across agents."""

    total_cost: str
    by_agent: list[UsageAggregateOut]
    by_model: list[UsageAggregateOut]


# --- schedules, triggers, and the fires either one produces ---------------------------
#
# Phase 3 — a team running without an operator at the keyboard. `ScheduleIn`/`TriggerIn`
# carry the same revision-selection shape (`revision_mode`/`pinned_revision_id`) and are
# validated the same way (`_revision_selection_is_coherent`) rather than sharing a base
# class: everything else about the two diverges (a cron expression against a market
# condition), and a base class for two fields would cost more to read than it saves to
# write.


def _revision_selection_is_coherent(revision_mode: str, pinned_revision_id: int | None) -> None:
    """specs/teams-schedules, "Harmonogram uruchamia rewizję przypiętą, a tryb «najnowsza»
    jest jawnym wyborem" — `pinned` names a revision, `latest` names none, and nothing
    else is well-formed."""
    if revision_mode == "pinned" and pinned_revision_id is None:
        raise ValueError("revision_mode 'pinned' needs pinned_revision_id")
    if revision_mode == "latest" and pinned_revision_id is not None:
        raise ValueError("revision_mode 'latest' must not carry pinned_revision_id")


class ScheduleIn(BaseModel):
    """What an operator submits to create or edit a schedule."""

    revision_mode: Literal["pinned", "latest"] = "pinned"
    pinned_revision_id: int | None = None
    cron_expression: str
    # Refused unless true, the day the pinned or latest revision's agents carry a
    # state-changing tool — `validation.check_unattended` is where that is enforced,
    # because it needs the revision's own definition, which this model does not carry
    # (specs/teams-schedules, "Harmonogram nad rewizją z narzędziami zapisującymi wymaga
    # jawnego potwierdzenia").
    unattended_ack: bool = False

    @field_validator("cron_expression")
    @classmethod
    def _cron_is_well_formed(cls, value: str) -> str:
        stripped = value.strip()
        if not croniter.is_valid(stripped):
            raise ValueError(f"{stripped!r} is not a valid five-field cron expression")
        return stripped

    @model_validator(mode="after")
    def _revision_selection(self) -> ScheduleIn:
        _revision_selection_is_coherent(self.revision_mode, self.pinned_revision_id)
        return self


class ScheduleOut(BaseModel):
    id: int
    team_id: int
    revision_mode: str
    pinned_revision_id: int | None
    cron_expression: str
    # Set at creation and after every claim — never read by a caller to decide anything,
    # only shown; the module is the one clock (specs/teams-schedules, "Moduł ma jeden
    # zegar i sam publikuje najbliższe wyzwolenia").
    next_fire_at: datetime
    enabled: bool
    disabled_reason: str | None
    consecutive_failures: int
    unattended_ack: bool
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
            next_fire_at=row["next_fire_at"],
            enabled=row["enabled"],
            disabled_reason=row["disabled_reason"],
            consecutive_failures=row["consecutive_failures"],
            unattended_ack=row["unattended_ack"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


class NextFiresOut(BaseModel):
    """specs/terminal-teams-schedules, "Terminal nie liczy czasu wyzwolenia sam" — the
    module's own answer to "when does this schedule fire next", computed fresh from
    `cron_expression` rather than read off the row's own `next_fire_at` — which reflects
    the last *claim*, not a live forecast, and goes stale the moment a schedule is
    disabled."""

    times: list[datetime]


class TriggerIn(BaseModel):
    """A market condition, expressed as a call to a tool this module already has a
    session for (specs/teams-triggers, "Warunek jest czytany narzędziami serwera
    narzędzi") — never a locally computed indicator. `field_path` names the value inside
    that call's result to compare; `threshold` is a string for the same reason every
    other number on this contract that a caller must not rescale is (see `CostLimits`)."""

    revision_mode: Literal["pinned", "latest"] = "pinned"
    pinned_revision_id: int | None = None
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    field_path: str
    comparison: Literal["gt", "gte", "lt", "lte", "eq"]
    threshold: str
    cooldown_seconds: int = 900
    poll_interval_seconds: int = 300
    unattended_ack: bool = False

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
    # `None` until the first check ever runs, and `None` again whenever the tool server
    # could not be asked — a third value, not a `false` (specs/teams-triggers,
    # "Niedostępność serwera narzędzi to nie jest niespełniony warunek").
    last_result: bool | None
    last_checked_at: datetime | None
    last_fired_at: datetime | None
    enabled: bool
    disabled_reason: str | None
    consecutive_failures: int
    unattended_ack: bool
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
            unattended_ack=row["unattended_ack"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


class ScheduleFireOut(BaseModel):
    """One fire attempt from either source, including one that started nothing
    (specs/teams-schedules, "Wyzwolenie bez przebiegu zostawia zapisany powód"). Exactly
    one of `schedule_id`/`trigger_id` is set, mirroring the row's own CHECK constraint."""

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
