"""What the operator may do with a candidate. Four decisions, none of them the agent's: a topic only proposes, and what the
archive reads and whom it follows stays with the person who looks at the list.

The channel decisions are decisions about the channel, so they settle its other open candidates too; the film decisions
settle one. A decision is refused, with a reason, before anything is written, and an undecided candidate stays undecided."""

from __future__ import annotations

from dataclasses import dataclass

from . import store
from .config import Settings
from .models import (
    ANALYSED_BY_HAND,
    CHANNEL_FOLLOWED,
    CHANNEL_IGNORED,
    DISMISSED,
    Candidate,
    Channel,
)
from .watchlist import Queued, WatchlistRefused, analyse_film, follow_channel


class CandidateMissing(Exception):
    """No candidate by that id."""


@dataclass(frozen=True, slots=True)
class FollowedFrom:
    channel: Channel
    created: bool


async def _open(conn, video_id: str) -> Candidate:
    found = await store.get_candidate(conn, video_id)
    if found is None:
        raise CandidateMissing(video_id)
    if found.decision is not None:
        raise WatchlistRefused(f"{found.title!r} has already been decided about ({found.decision})")
    return found


def _channel_of(candidate: Candidate) -> str:
    if candidate.channel_id is None:
        raise WatchlistRefused(f"the source named no channel for {candidate.title!r}")
    return candidate.channel_id


async def follow_channel_of(pool, providers, settings: Settings, video_id: str, *, prompt: int | None) -> FollowedFrom:
    """Follow the candidate's channel, under the watch list's ceiling and its prompt rules like any other following."""
    async with pool.acquire() as conn:
        candidate = await _open(conn, video_id)
    channel_id = _channel_of(candidate)
    followed = await follow_channel(
        pool, providers.source, settings, channel_id, added_by="operator", prompt=prompt
    )
    now = providers.clock.now()
    async with pool.acquire() as conn, conn.transaction():
        await store.decide_candidate(conn, video_id, CHANNEL_FOLLOWED, at=now)
        await store.decide_channel_candidates(conn, channel_id, CHANNEL_FOLLOWED, at=now)
    return FollowedFrom(followed.channel, followed.created)


async def analyse_candidate(pool, providers, settings: Settings, video_id: str, *, prompt: int | None) -> Queued:
    """Name the candidate's film for analysis, as if the operator had pasted its address."""
    async with pool.acquire() as conn:
        await _open(conn, video_id)
    queued = await analyse_film(pool, providers, settings, video_id, prompt=prompt)
    async with pool.acquire() as conn:
        await store.decide_candidate(conn, video_id, ANALYSED_BY_HAND, at=providers.clock.now())
    return queued


async def dismiss(pool, clock, video_id: str) -> Candidate:
    async with pool.acquire() as conn:
        await _open(conn, video_id)
        decided = await store.decide_candidate(conn, video_id, DISMISSED, at=clock.now())
    assert decided is not None
    return decided


async def ignore_channel_of(pool, clock, video_id: str) -> Candidate:
    """The channel's films stop becoming candidates, and the ones already offered are taken off the list."""
    async with pool.acquire() as conn:
        candidate = await _open(conn, video_id)
        channel_id = _channel_of(candidate)
        now = clock.now()
        async with conn.transaction():
            await store.ignore_channel(conn, channel_id, candidate.channel_title)
            decided = await store.decide_candidate(conn, video_id, CHANNEL_IGNORED, at=now)
            await store.decide_channel_candidates(conn, channel_id, CHANNEL_IGNORED, at=now)
    assert decided is not None
    return decided
