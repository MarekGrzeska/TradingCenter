"""The prompts' words, for the operator's own client only. Registered on the server mounted at `/mcp`, whose one caller is
the operator's Claude Code, and on no server this process's models call: a model that could rewrite a prompt could rewrite
what reaches the operator's phone."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from .. import prompts, store
from ..models import Prompt
from ._shared import READ_ONLY, ToolContext, refused

# Every version is kept and the same words make none, so an edit is neither destructive nor different the second time.
EDITS = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)

LIST_THEM = "youtube_archive_status lists the prompts by name"


class PromptText(BaseModel):
    name: str
    version: int = Field(description="a reading names the version it was made by")
    body: str


class PromptEdited(PromptText):
    replaced: str = Field(description="the words of the version before, as they were")


def _text(prompt: Prompt) -> PromptText:
    return PromptText(name=prompt.name, version=prompt.version, body=prompt.body)


def register(mcp: FastMCP, ctx: ToolContext) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def read_prompt(prompt: str) -> PromptText | dict:
        """The words a prompt, named as youtube_archive_status lists it, reads films by — at its latest version."""
        async with ctx.pool.acquire() as conn:
            found = await store.prompt_named(conn, prompt)
        if found is None:
            return refused(f"there is no prompt {prompt!r}", LIST_THEM)
        return _text(found)

    @mcp.tool(annotations=EDITS)
    async def edit_prompt(prompt: str, body: str) -> PromptEdited | dict:
        """Replace a prompt's words with `body`, as a new version: every film read from now on is read by it, and
        readings already made keep the version they were made by. The words lay out the reading the operator's alert
        sends, so they decide what reaches the phone."""
        async with ctx.pool.acquire() as conn:
            found = await store.prompt_named(conn, prompt)
        if found is None:
            return refused(f"there is no prompt {prompt!r}", LIST_THEM)
        try:
            edited = await prompts.update(ctx.pool, found.id, name=None, body=body)
        except prompts.PromptRefused as err:
            return refused(str(err), "change the words and try again")
        if edited is None:
            return refused(f"{prompt!r} was deleted a moment ago", LIST_THEM)
        return PromptEdited(**_text(edited).model_dump(), replaced=found.body)
