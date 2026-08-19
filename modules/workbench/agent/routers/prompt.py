"""`GET`/`PUT /prompt` — the system prompt's own trusted storage, read and rewritten
here instead of a constant in `agent/prompt.py` (specs/agent-prompt-management).

Global to the module, not scoped to an owner: one prompt, not one per operator, so
`current_principal` is asked only to refuse an unauthenticated request — its value is
never read.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from .. import store
from ..auth import current_principal
from ..contract import PromptOut, PromptUpdateIn

router = APIRouter()


@router.get("/prompt")
async def get_prompt(request: Request, _: str = Depends(current_principal)) -> PromptOut:
    async with request.app.state.agent.pool.acquire() as conn:
        revision = await store.latest_prompt_revision(conn)
    return PromptOut.from_revision(revision)


@router.put("/prompt")
async def update_prompt(
    body: PromptUpdateIn, request: Request, _: str = Depends(current_principal)
) -> PromptOut:
    async with request.app.state.agent.pool.acquire() as conn:
        revision = await store.create_prompt_revision(
            conn, with_tools_body=body.with_tools, without_tools_body=body.without_tools
        )
    return PromptOut.from_revision(revision)
