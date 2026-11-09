"""The closed catalogue of recipes a step may run (`teams-steps`). A recipe is code in this package; a revision only names
one and fills its parameters, so a new recipe is a deploy and a new team is not."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

ParamType = Literal["integer", "decimal", "text"]


@dataclass(frozen=True)
class ParamSpec:
    """One parameter as the terminal's form and the team tools see it — the types the first recipe needs, no more."""

    name: str
    type: ParamType
    required: bool
    description: str
    default: Any = None


@dataclass(frozen=True)
class Recipe:
    name: str
    description: str
    params_model: type[BaseModel]
    params: tuple[ParamSpec, ...]
    # Every tool the recipe calls, resolved through the run's plan under the step's key like an agent's assignment.
    tools: tuple[str, ...]


class StrategyExecuteParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_id: int = Field(gt=0)
    revision: int = Field(gt=0)
    symbol: str
    # A decimal string, as every number this module compares rather than computes; None means the document's own rule.
    deposit_fraction: str | None = None
    wait_for_bar_seconds: int = Field(default=30, ge=0, le=120)
    max_bar_age_seconds: int | None = Field(default=None, gt=0)

    @field_validator("symbol")
    @classmethod
    def _symbol_named(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("symbol must not be blank")
        return value.strip()

    @field_validator("deposit_fraction")
    @classmethod
    def _fraction(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            parsed = Decimal(value)
        except InvalidOperation as err:
            raise ValueError(f"deposit_fraction is not a number: {value!r}") from err
        if not Decimal(0) < parsed <= Decimal(1):
            raise ValueError(f"deposit_fraction must be above 0 and at most 1, got {value}")
        return str(parsed)


STRATEGY_EXECUTE = Recipe(
    name="strategy_execute",
    description=(
        "Keeps this team's own position in line with a strategy's engine (strategy_signal): enters on a fresh "
        "`enter` with a market order sized from the deposit, closes its own position on `exit` or when the engine "
        "holds none, never catches up a stale entry and never reverses in one run. One attempt per signal bar. "
        "Market orders without stop or target only; any other strategy ends as unsupported."
    ),
    params_model=StrategyExecuteParams,
    params=(
        ParamSpec("strategy_id", "integer", True, "the strategy to execute"),
        ParamSpec("revision", "integer", True, "the strategy's revision"),
        ParamSpec("symbol", "text", True, "the instrument the strategy trades, e.g. US100"),
        ParamSpec(
            "deposit_fraction",
            "decimal",
            False,
            "deposit per position as a fraction of equity, e.g. 0.35; empty means the strategy document's sizing",
        ),
        ParamSpec(
            "wait_for_bar_seconds", "integer", False, "how long to wait for the signal bar in the archive", 30
        ),
        ParamSpec(
            "max_bar_age_seconds",
            "integer",
            False,
            "an entry on a signal bar older than this is skipped; empty means no limit",
        ),
    ),
    tools=(
        "strategy_signal",
        "get_positions",
        "get_working_orders",
        "get_balance",
        "size_for_margin",
        "place_order",
        "close_position",
        "get_last_price",
        "get_candles",
    ),
)

RECIPES: dict[str, Recipe] = {recipe.name: recipe for recipe in (STRATEGY_EXECUTE,)}


class RecipeRefused(ValueError):
    """A step naming no known recipe, or parameters the recipe does not take."""


def parse_params(recipe_name: str, params: dict[str, Any]) -> BaseModel:
    """The step's parameters as the recipe's own model, or a refusal saying which parameter and why."""
    recipe = RECIPES.get(recipe_name)
    if recipe is None:
        raise RecipeRefused(f"unknown recipe {recipe_name!r} — known recipes are {sorted(RECIPES)}")
    try:
        return recipe.params_model.model_validate(params)
    except ValidationError as err:
        first = err.errors()[0]
        where = ".".join(str(part) for part in first["loc"]) or "params"
        raise RecipeRefused(f"parameter {where!r}: {first['msg']}") from None
