"""Running a step's recipe: the one place a recipe's name becomes code."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ..contract import StepDefinition
from . import strategy_execute, telegram_report
from .runtime_types import StepContext


async def run_recipe(step: StepDefinition, ctx: StepContext, given: Sequence[tuple[str, str]]) -> dict[str, Any]:
    if step.recipe == "strategy_execute":
        return await strategy_execute.execute(step, ctx)
    if step.recipe == "telegram_report":
        return await telegram_report.execute(step, ctx, given)
    raise ValueError(f"step {step.key!r} names recipe {step.recipe!r}, which this module does not run")
