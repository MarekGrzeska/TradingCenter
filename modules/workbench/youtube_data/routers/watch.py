"""The watch list: what the operator follows. The operator adds, pauses and — alone — takes off; the agent's tools add and
never remove, which is why removal is a route here and not a tool anywhere."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, status

from .. import store, watchlist
from ..analysis import PROFILES
from ..contract import (
    ChannelAddedOut,
    ChannelIn,
    ChannelOut,
    ChannelPatch,
    ChannelsOut,
    Problem,
    TopicAddedOut,
    TopicIn,
    TopicOut,
    TopicPatch,
    TopicsOut,
)
from ..watchlist import WatchlistRefused
from .deps import connection

router = APIRouter(tags=["watch list"])


def _refuse(detail: str) -> HTTPException:
    return HTTPException(
        status.HTTP_422_UNPROCESSABLE_CONTENT, detail=Problem(detail=detail, cause="request").model_dump()
    )


def _missing(what: str) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, detail=Problem(detail=what).model_dump())


@router.get("/channels", response_model=ChannelsOut)
async def channels(request: Request) -> ChannelsOut:
    async with connection(request.app.state.pool) as conn:
        found = await store.list_channels(conn)
    return ChannelsOut(
        channels=[ChannelOut.of(channel) for channel in found], ceiling=request.app.state.settings.max_channels
    )


@router.post("/channels", response_model=ChannelAddedOut, responses={422: {"model": Problem}})
async def follow(request: Request, body: ChannelIn) -> ChannelAddedOut:
    """Follow a channel by id, `@handle` or address. Following one that is already followed changes nothing about it."""
    state = request.app.state
    try:
        followed = await watchlist.follow_channel(
            state.pool,
            state.providers.source,
            state.settings,
            body.reference,
            added_by="operator",
            profile=body.profile,
            language=body.language,
        )
    except WatchlistRefused as err:
        raise _refuse(str(err)) from err
    return ChannelAddedOut(channel=ChannelOut.of(followed.channel), created=followed.created)


@router.patch(
    "/channels/{channel_id}",
    response_model=ChannelOut,
    responses={404: {"model": Problem}, 422: {"model": Problem}},
)
async def patch_channel(request: Request, channel_id: str, body: ChannelPatch) -> ChannelOut:
    if body.profile is not None and body.profile not in PROFILES:
        raise _refuse(f"profile must be one of {', '.join(PROFILES)}; got {body.profile!r}")
    async with connection(request.app.state.pool) as conn:
        updated = await store.update_channel(
            conn, channel_id, profile=body.profile, active=body.active
        )
    if updated is None:
        raise _missing(f"no channel {channel_id!r} on the list")
    return ChannelOut.of(updated)


@router.delete(
    "/channels/{channel_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"model": Problem}},
)
async def unfollow(request: Request, channel_id: str) -> Response:
    """Take a channel off. Its films and their readings stay: the list is why we looked, not what we keep."""
    async with connection(request.app.state.pool) as conn:
        removed = await store.remove_channel(conn, channel_id)
    if not removed:
        raise _missing(f"no channel {channel_id!r} on the list")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/topics", response_model=TopicsOut)
async def topics(request: Request) -> TopicsOut:
    state = request.app.state
    async with connection(state.pool) as conn:
        found = await store.list_topics(conn)
    return TopicsOut(
        topics=[TopicOut.of(topic) for topic in found],
        ceiling=state.settings.max_topics,
    )


@router.post("/topics", response_model=TopicAddedOut, responses={422: {"model": Problem}})
async def add_topic(request: Request, body: TopicIn) -> TopicAddedOut:
    state = request.app.state
    try:
        added = await watchlist.add_topic(
            state.pool,
            state.settings,
            body.phrase,
            added_by="operator",
            language=body.language,
            interval_minutes=body.interval_minutes,
            max_videos_per_run=body.max_videos_per_run,
            profile=body.profile,
        )
    except WatchlistRefused as err:
        raise _refuse(str(err)) from err
    return TopicAddedOut(
        topic=TopicOut.of(added.topic), created=added.created, defaults_applied=list(added.defaults_applied)
    )


@router.patch("/topics/{topic_id}", response_model=TopicOut, responses={404: {"model": Problem}})
async def patch_topic(request: Request, topic_id: int, body: TopicPatch) -> TopicOut:
    async with connection(request.app.state.pool) as conn:
        updated = await store.update_topic(conn, topic_id, active=body.active)
    if updated is None:
        raise _missing(f"no topic {topic_id} on the list")
    return TopicOut.of(updated)


@router.delete(
    "/topics/{topic_id}", status_code=status.HTTP_204_NO_CONTENT, responses={404: {"model": Problem}}
)
async def remove_topic(request: Request, topic_id: int) -> Response:
    async with connection(request.app.state.pool) as conn:
        removed = await store.remove_topic(conn, topic_id)
    if not removed:
        raise _missing(f"no topic {topic_id} on the list")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
