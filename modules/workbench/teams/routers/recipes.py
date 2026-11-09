"""`GET /teams/step-recipes` — the closed catalogue of what a step may run, read by the terminal's step editor and by the
team tools. Published from code, because the catalogue is code: a revision names a recipe, it never carries one."""

from __future__ import annotations

from fastapi import APIRouter

from ..contract import StepParamOut, StepRecipeOut
from ..steps import RECIPES

router = APIRouter()


@router.get("/step-recipes")
async def list_step_recipes() -> list[StepRecipeOut]:
    return [
        StepRecipeOut(
            name=recipe.name,
            description=recipe.description,
            params=[
                StepParamOut(
                    name=spec.name,
                    type=spec.type,
                    required=spec.required,
                    description=spec.description,
                    default=spec.default,
                )
                for spec in recipe.params
            ],
            tools=list(recipe.tools),
        )
        for recipe in RECIPES.values()
    ]
