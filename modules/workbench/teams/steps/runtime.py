"""Running a step's recipe: the one place a recipe's name becomes code."""

from __future__ import annotations

from typing import Any

from ..contract import StepDefinition
from . import strategy_execute
from .runtime_types import StepContext


async def run_recipe(step: StepDefinition, ctx: StepContext) -> dict[str, Any]:
    if step.recipe == "strategy_execute":
        return await strategy_execute.execute(step, ctx)
    raise ValueError(f"step {step.key!r} names recipe {step.recipe!r}, which this module does not run")
