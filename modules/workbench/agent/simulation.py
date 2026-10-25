"""A model that answers from a scenario file (`agent-simulated-model`): the end-to-end stack's conversation, which has to
go through a real turn, real tools and the real terminal without a call leaving this process. Refused where
DATABASE_USER is set (`config.py`), so it cannot answer on a deployment.

    {"turns": [{"when": "^E2E szkic (?<id>\\\\d+)$",
                "rounds": [{"tools": [{"name": "draft_strategy", "arguments": {"strategy_id": "{id}", ...}}]},
                           {"say": "Wpisałem szkic."}]}]}

The first rule whose `when` matches the whole of the operator's last message decides the turn; the turn's n-th call to
the model plays `rounds[n]`, which is the count of tool rounds the turn already passes in.
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator, Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from .provider import (
    Conversation,
    ProviderChunk,
    TextDelta,
    ToolCallRequest,
    ToolRound,
    UsageReport,
)

# Measured, not unknown: nothing was consumed, and `agent-usage` tells zero from "the provider did not say".
_NOTHING_USED = UsageReport(input_tokens=0, output_tokens=0, cached_tokens=None, reasoning_tokens=None)
_PLACEHOLDER = re.compile(r"\{(\w+)\}")


class ScenarioError(Exception):
    """The scenario cannot be read or breaks its rules — a refusal to start, not a puzzle in the third test."""


class ToolAsk(BaseModel):
    name: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)


class Round(BaseModel):
    tools: list[ToolAsk] | None = None
    say: str | None = None

    @model_validator(mode="after")
    def _one_or_the_other(self) -> Round:
        if (self.tools is None) == (self.say is None) or self.tools == []:
            raise ValueError("a round is either a non-empty `tools` list or a `say` text")
        return self


class Rule(BaseModel):
    when: re.Pattern[str]
    rounds: list[Round] = Field(min_length=1)

    @field_validator("when", mode="before")
    @classmethod
    def _python_named_groups(cls, value: object) -> object:
        # Written the way JavaScript and the docs spell a named group, `(?<id>…)`; Python wants `(?P<id>…)`.
        return re.sub(r"\(\?<(?=\w)", "(?P<", value) if isinstance(value, str) else value

    @model_validator(mode="after")
    def _ends_by_saying(self) -> Rule:
        if self.rounds[-1].say is None:
            raise ValueError(f"the last round of {self.when.pattern!r} must be a `say`: a turn ends in text")
        return self


class Scenario(BaseModel):
    turns: list[Rule] = Field(min_length=1)

    def rule_for(self, message: str) -> Rule | None:
        return next((rule for rule in self.turns if rule.when.fullmatch(message)), None)


def load_scenario(path: str | Path) -> Scenario:
    try:
        return Scenario.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, ValidationError) as err:
        raise ScenarioError(f"the scenario {path} cannot be used: {err}") from err


def _filled(value: Any, groups: dict[str, str]) -> Any:
    if isinstance(value, dict):
        return {key: _filled(item, groups) for key, item in value.items()}
    if isinstance(value, list):
        return [_filled(item, groups) for item in value]
    if not isinstance(value, str):
        return value
    whole = _PLACEHOLDER.fullmatch(value)
    if whole and whole.group(1) in groups and groups[whole.group(1)].isdigit():
        # A tool's id parameter is an integer, and a scenario written in JSON has only strings to carry a group in.
        return int(groups[whole.group(1)])
    return _PLACEHOLDER.sub(lambda m: groups.get(m.group(1), m.group(0)), value)


class SimulatedProvider:
    """`ModelProvider` without a model. Each call yields one round of the matched rule and a zero usage report."""

    def __init__(self, scenario: Scenario) -> None:
        self._scenario = scenario

    async def stream(
        self,
        *,
        model: str,
        system_prompt: str,
        given: Any,
        tools: Sequence[Any] = (),
        rounds: Sequence[ToolRound] = (),
    ) -> AsyncIterator[ProviderChunk]:
        del model, system_prompt, tools
        message = _last_operator_message(given)
        rule = self._scenario.rule_for(message)
        if rule is None:
            yield TextDelta(f"(scenariusz nie zna tej wiadomości: {message!r})")
            yield _NOTHING_USED
            return
        match = rule.when.fullmatch(message)
        groups = {k: v for k, v in (match.groupdict() if match else {}).items() if v is not None}
        step = rule.rounds[min(len(rounds), len(rule.rounds) - 1)]
        if step.say is not None:
            yield TextDelta(step.say)
        for index, ask in enumerate(step.tools or []):
            yield ToolCallRequest(id=f"sim-{len(rounds)}-{index}", name=ask.name, arguments=_filled(ask.arguments, groups))
        yield _NOTHING_USED


def _last_operator_message(given: Any) -> str:
    if isinstance(given, Conversation):
        return next((content for role, content in reversed(given.turns) if role == "operator"), "")
    return getattr(given, "text", "")
