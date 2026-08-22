"""The rules about what may be tracked, in the one place both surfaces go through.

The REST contract and the tool surface are two doors to the same decision, and the ceiling
has to hold at both. Written here rather than in each router because a limit enforced in one
of two places is a limit the other one does not have — and the door without it is the tool
surface, where a model asked to "add whatever looks interesting" is the case the ceiling
exists for.
"""

from __future__ import annotations

from tc_runtime.db import Conn

from . import store
from .models import Event


class TrackingRefused(Exception):
    """Refused for a reason the caller can act on. The message is written to be read by a
    model as well as by an operator: it says what happened and what to do first."""


class LimitReached(TrackingRefused):
    pass


class UnknownEvent(TrackingRefused):
    """The provider does not have this event — an answer to the question, not a failure of
    this module, and the two must not read alike."""


async def track(
    conn: Conn,
    event: Event,
    *,
    max_tracked_events: int,
    group_id: int | None = None,
) -> tuple[int, bool]:
    """Brings an event under observation. Returns `(event_id, was_already_tracked)`.

    Already tracked is not an error and does not make a second observation: a repeat may
    move the event to a different group and says so, which is what lets a model call this
    without first having to remember whether it called it before.

    The ceiling is checked only for an event that is not already tracked. A refresh of
    something already being watched adds no traffic, so refusing it at the limit would make
    a full archive unable to notice a market being added to an event it already holds.
    """
    existing = await store.load_events(conn, provider_event_id=event.provider_event_id)
    already_tracking = bool(existing) and existing[0].tracking

    if not already_tracking:
        tracked = await store.count_tracked(conn)
        if tracked >= max_tracked_events:
            raise LimitReached(
                f"already tracking {tracked} events, which is the configured ceiling "
                f"({max_tracked_events}). End the observation of one before adding "
                "another — nothing has been changed."
            )

    # `resume=True` only here: this is the act that brings an event under observation, so
    # it is the one that may clear an earlier ending. The sampler's own refresh must not.
    event_id = await store.upsert_event(conn, event, group_id=group_id, resume=True)
    return event_id, already_tracking


async def untrack(conn: Conn, provider_event_id: str) -> bool:
    """Stops the sampling and keeps every sample. Deleting collected history is a different
    act on a different surface, and no tool reaches it."""
    return await store.end_tracking(conn, provider_event_id)
