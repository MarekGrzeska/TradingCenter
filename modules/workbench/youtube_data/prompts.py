"""What the operator may do with prompts; the agent only chooses one. One set of functions serves the routes and the tools.

A prompt never changes what a transcript is or the answer's shape — `analysis.system_message` keeps that."""

from __future__ import annotations

import asyncpg

from . import budget, store
from .analysis import MAX_PROMPT_CHARS
from .models import Prompt

MAX_NAME_CHARS = 80
# The list a person picks from; a bigger one is a sign the prompts are being used as notes.
MAX_PROMPTS = 50


class PromptRefused(Exception):
    """The request cannot be done, and this says why in words meant for whoever asked."""


def _clean(name: str | None, body: str | None) -> tuple[str | None, str | None]:
    if name is not None:
        name = " ".join(name.split())
        if not name or len(name) > MAX_NAME_CHARS:
            raise PromptRefused(f"a prompt's name is 1 to {MAX_NAME_CHARS} characters")
    if body is not None:
        body = body.strip()
        if not body or len(body) > MAX_PROMPT_CHARS:
            raise PromptRefused(f"a prompt's text is 1 to {MAX_PROMPT_CHARS} characters")
    return name, body


async def create(pool, *, name: str, body: str) -> Prompt:
    clean_name, clean_body = _clean(name, body)
    assert clean_name is not None and clean_body is not None
    async with pool.acquire() as conn:
        if await store.count_prompts(conn) >= MAX_PROMPTS:
            raise PromptRefused(f"there are {MAX_PROMPTS} prompts, which is the ceiling — delete one first")
        try:
            return await store.create_prompt(conn, name=clean_name, body=clean_body)
        except asyncpg.UniqueViolationError as err:
            raise PromptRefused(f"a prompt named {clean_name!r} already exists") from err


async def update(pool, prompt_id: int, *, name: str | None, body: str | None) -> Prompt | None:
    """`None` where there is no such prompt. New words make a new version; a new name makes none."""
    clean_name, clean_body = _clean(name, body)
    async with pool.acquire() as conn:
        try:
            return await store.update_prompt(conn, prompt_id, name=clean_name, body=clean_body)
        except asyncpg.UniqueViolationError as err:
            if clean_name is None:
                raise PromptRefused("the prompt was saved at the same moment from elsewhere — reload and try again") from err
            raise PromptRefused(f"a prompt named {clean_name!r} already exists") from err


async def delete(pool, prompt_id: int) -> bool:
    """False where there is no such prompt. Refused for the seeded one and for one a channel or a topic still reads by."""
    async with pool.acquire() as conn:
        found = await store.get_prompt(conn, prompt_id)
        if found is None:
            return False
        if found.seeded:
            raise PromptRefused(f"{found.name!r} is the prompt that is always there — edit it, it cannot be deleted")
        channels, topics = (await store.prompt_assignments(conn)).get(prompt_id, ([], []))
        if channels or topics:
            using = [f"channel {title}" for title in channels] + [f"topic {phrase!r}" for phrase in topics]
            raise PromptRefused(f"{found.name!r} is still read by {', '.join(using)} — give them another prompt first")
        if not await store.delete_prompt(conn, prompt_id):
            raise PromptRefused(f"{found.name!r} was taken by a channel or a topic a moment ago — try again")
        return True


async def resolve(conn, choice: int | str | None) -> int:
    """The prompt a caller chose, by id or by name — the seeded one where it chose none."""
    if choice is None:
        return (await store.seeded_prompt(conn)).id
    found = await (store.get_prompt(conn, choice) if isinstance(choice, int) else store.prompt_named(conn, choice))
    if found is None:
        raise PromptRefused(f"there is no prompt {choice!r} — the prompts on offer are in youtube_archive_status")
    return found.id


async def order_reading(
    pool, settings, clock, video_id: str, choice: int | str | None, *, model_configured: bool
) -> int:
    """Which prompt a film is to be read by once more, or why not: no model, no film, no words yet, or no tokens left."""
    if not model_configured:
        raise PromptRefused("no model is configured, so nothing can be read — youtube_archive_status says so")
    async with pool.acquire() as conn:
        prompt_id = await resolve(conn, choice)
        if await store.get_video(conn, video_id) is None:
            raise PromptRefused(f"no film {video_id!r} is in this archive")
        if not await store.has_transcript(conn, video_id):
            raise PromptRefused(f"{video_id!r} has no transcript yet, so there is nothing to read — it is still on its road")
        ceiling = budget.Ceiling(budget.ANALYSER, budget.TOKENS, settings.daily_token_limit)
        if await budget.remaining(conn, ceiling, day=budget.utc_day(clock.now())) <= 0:
            raise PromptRefused("the day's tokens are spent; readings start again at midnight UTC")
    return prompt_id
