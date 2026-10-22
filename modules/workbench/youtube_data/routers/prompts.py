"""The prompts a film is read by. The operator writes, edits and — alone — deletes them; the agent's tools only choose one,
which is why creating and deleting are routes here and not tools anywhere."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, status

from .. import prompts, store
from ..analysis import MAX_PROMPT_CHARS
from ..contract import Problem, PromptIn, PromptOut, PromptPatch, PromptsOut
from .deps import connection

router = APIRouter(tags=["prompts"])


def _refuse(detail: str) -> HTTPException:
    return HTTPException(
        status.HTTP_422_UNPROCESSABLE_CONTENT, detail=Problem(detail=detail, cause="request").model_dump()
    )


def _missing(prompt_id: int) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, detail=Problem(detail=f"no prompt {prompt_id}").model_dump())


async def _out(pool, prompt) -> PromptOut:
    async with connection(pool) as conn:
        channels, topics = (await store.prompt_assignments(conn)).get(prompt.id, ([], []))
    return PromptOut.of(prompt, channels, topics)


@router.get("/prompts", response_model=PromptsOut)
async def list_prompts(request: Request) -> PromptsOut:
    async with connection(request.app.state.pool) as conn:
        found = await store.list_prompts(conn)
        assigned = await store.prompt_assignments(conn)
    return PromptsOut(
        prompts=[PromptOut.of(prompt, *assigned.get(prompt.id, ([], []))) for prompt in found],
        max_chars=MAX_PROMPT_CHARS,
        ceiling=prompts.MAX_PROMPTS,
    )


@router.post("/prompts", response_model=PromptOut, status_code=status.HTTP_201_CREATED, responses={422: {"model": Problem}})
async def create_prompt(request: Request, body: PromptIn) -> PromptOut:
    try:
        created = await prompts.create(request.app.state.pool, name=body.name, body=body.body)
    except prompts.PromptRefused as err:
        raise _refuse(str(err)) from err
    return await _out(request.app.state.pool, created)


@router.patch(
    "/prompts/{prompt_id}",
    response_model=PromptOut,
    responses={404: {"model": Problem}, 422: {"model": Problem}},
)
async def patch_prompt(request: Request, prompt_id: int, body: PromptPatch) -> PromptOut:
    """New words make a new version; the readings the old ones made keep saying which version that was."""
    try:
        updated = await prompts.update(request.app.state.pool, prompt_id, name=body.name, body=body.body)
    except prompts.PromptRefused as err:
        raise _refuse(str(err)) from err
    if updated is None:
        raise _missing(prompt_id)
    return await _out(request.app.state.pool, updated)


@router.delete(
    "/prompts/{prompt_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"model": Problem}, 422: {"model": Problem}},
)
async def delete_prompt(request: Request, prompt_id: int) -> Response:
    """Refused for the seeded prompt and for one a channel or a topic still reads by. The readings it made stay."""
    try:
        removed = await prompts.delete(request.app.state.pool, prompt_id)
    except prompts.PromptRefused as err:
        raise _refuse(str(err)) from err
    if not removed:
        raise _missing(prompt_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
