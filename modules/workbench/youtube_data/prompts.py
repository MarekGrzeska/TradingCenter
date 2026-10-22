"""What the operator may do with prompts, and what the agent may do with them: choose one. The same functions serve the REST
routes and the tools, so a refusal is one rule and not two that agree today.

A prompt says what to look for in a film and how to lay the text out. It does not say what a transcript is or what shape the
answer has — `analysis.system_message` keeps that, so no prompt can change it. Deleting is the operator's alone, and never
leaves a channel or a topic without a prompt to read by."""

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
        if len(await store.list_prompts(conn)) >= MAX_PROMPTS:
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
            raise PromptRefused(f"a prompt named {clean_name!r} already exists") from err


async def delete(pool, prompt_id: int) -> bool:
    """False where there is no such prompt. Refused for the seeded one — there is always at least one — and for one a
    channel or a topic still reads by, naming them."""
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
        return await store.delete_prompt(conn, prompt_id)


async def resolve(conn, choice: int | str | None) -> int:
    """The prompt a caller chose, by id or by name — the seeded one where it chose none."""
    if choice is None:
        return (await store.seeded_prompt(conn)).id
    found = await (store.get_prompt(conn, choice) if isinstance(choice, int) else store.prompt_named(conn, choice))
    if found is None:
        raise PromptRefused(f"there is no prompt {choice!r} — the prompts on offer are in youtube_archive_status")
    return found.id


async def order_reading(pool, settings, clock, video_id: str, choice: int | str | None) -> int:
    """Checks that a film can be read once more by the chosen prompt, and says which prompt that is. Refuses where the film
    is not in the archive, has no words yet — the transcript is Gemini's, and this does not ask for one — or the day's
    tokens are spent."""
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
