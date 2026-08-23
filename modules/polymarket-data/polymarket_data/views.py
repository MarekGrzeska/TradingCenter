"""Assembling what a read answers with, in one place both surfaces use.

The REST contract and the tool surface answer the same questions in different shapes, and
the part that is genuinely the same — which events, with which prices, and whether collection
is actually running — is here rather than twice.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from tc_runtime.db import Conn

from . import store
from .contract import CollectionOut, SnapshotEntry, SnapshotOut, TrackedEventOut
from .models import Event, Sample

# How many missed ticks before collection is called stalled rather than merely quiet. Three,
# so one slow round or one provider hiccup does not raise an alarm — but silence in the data
# still stops looking like silence in the market.
STALLED_AFTER_TICKS = 3


def collection_state(
    event: Event,
    state: dict | None,
    *,
    interval_seconds: int,
    now: datetime | None = None,
) -> CollectionOut:
    """Whether prices are actually arriving for this event.

    Being on the list does not prove they are, and that is the whole reason this exists:
    an observation nobody is collecting looks exactly like a market nobody is trading.
    """
    moment = now or datetime.now(UTC)
    last = (state or {}).get("last_success_at")

    if event.resolved:
        return CollectionOut(state="resolved", last_sample_at=last)

    failures = (state or {}).get("consecutive_failures") or 0
    reason = (state or {}).get("last_failure_reason")
    stale = last is None or moment - last > timedelta(seconds=interval_seconds * STALLED_AFTER_TICKS)
    if failures or stale:
        return CollectionOut(
            state="stalled",
            last_sample_at=last,
            reason=reason or "no sample has arrived within the last few ticks",
        )
    return CollectionOut(state="collecting", last_sample_at=last)


async def tracked_events(
    conn: Conn,
    *,
    interval_seconds: int,
    group_id: int | None = None,
    provider_event_id: str | None = None,
) -> list[TrackedEventOut]:
    events = await store.load_events(
        conn,
        group_id=group_id,
        provider_event_id=provider_event_id,
    )
    if not events:
        return []
    samples = await store.latest_samples(conn)
    states = await store.sampling_state(conn)
    return [
        TrackedEventOut.of(
            event,
            samples,
            collection_state(
                event, states.get(event.id or 0), interval_seconds=interval_seconds
            ),
        )
        for event in events
    ]


async def snapshot(conn: Conn) -> SnapshotOut:
    """Every tracked outcome's newest price, in one read.

    The view the terminal opens on. A request per event would be a request per row, and one
    measured event holds 128 markets.
    """
    events = await store.load_events(conn)
    samples: dict[int, Sample] = await store.latest_samples(conn)
    entries: list[SnapshotEntry] = []
    for event in events:
        for market in event.markets:
            for outcome in market.outcomes:
                sample = samples.get(outcome.id or 0)
                entries.append(
                    SnapshotEntry(
                        event_id=event.id or 0,
                        event_slug=event.slug,
                        market_id=market.id or 0,
                        market_label=market.group_item_title,
                        outcome_id=outcome.id or 0,
                        outcome_name=outcome.name,
                        price=float(sample.midpoint)
                        if sample and sample.midpoint is not None
                        else None,
                        price_at=sample.observed_at if sample else None,
                    )
                )
    return SnapshotOut(entries=entries)
