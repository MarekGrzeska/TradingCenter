"""The rules about what may be tracked, in the one place both surfaces go through. A limit enforced in
one of two doors is a limit the other does not have — and the other is the tool surface."""

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
    """Brings an event under observation. Already tracked is not an error and makes no second observation.
    The ceiling is checked only for a new event: a refresh adds no traffic, and refusing it would freeze a full archive."""
    existing = await store.load_events(conn, provider_event_id=event.provider_event_id)
    already_tracking = bool(existing)

    if not already_tracking:
        tracked = await store.count_tracked(conn)
        if tracked >= max_tracked_events:
            raise LimitReached(
                f"already tracking {tracked} events, which is the configured ceiling "
                f"({max_tracked_events}). Making room means removing an observation with "
                "everything collected for it, which is the operator's to do in the "
                "terminal — nothing has been changed here."
            )

    event_id = await store.upsert_event(conn, event, group_id=group_id)
    return event_id, already_tracking
