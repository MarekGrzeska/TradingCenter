"""Reads that both surfaces make, in one place — the REST routes and the tools ask the same questions, and answering them
twice is how the two would come to disagree."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from tc_runtime.db import Conn

from . import budget, store
from .config import Settings
from .contract import LoopOut, ProviderOut, StateOut, VideoOut, VideosOut
from .providers.build import Providers

# How far back the finished-films counts look, and how many missed passes make the loop stale.
RECENT_DAYS = 7
STALE_AFTER_PASSES = 3.0


def window(
    *,
    hours: int | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    default_hours: int = 24,
    now: datetime | None = None,
) -> tuple[datetime, datetime]:
    """The window a caller asked for, as two instants. `hours` and an explicit range are two ways of saying the same thing,
    and the explicit one wins where both arrive."""
    # A bound without a zone is read as UTC: compared with an aware one it would be a `TypeError`, not a refusal.
    since, until = (_aware(bound) for bound in (since, until))
    end = until or (now or datetime.now(UTC))
    if since is not None:
        return since, end
    return end - timedelta(hours=hours or default_hours), end


def _aware(bound: datetime | None) -> datetime | None:
    return bound.replace(tzinfo=UTC) if bound is not None and bound.tzinfo is None else bound


async def videos(
    conn: Conn,
    *,
    start: datetime,
    end: datetime,
    channel_id: str | None = None,
    topic_id: int | None = None,
    instrument: str | None = None,
    min_score: int | None = None,
    state: str | None = None,
    limit: int,
) -> VideosOut:
    found = await store.list_films(
        conn,
        start=start,
        end=end,
        channel_id=channel_id,
        origin=None if topic_id is None else f"topic:{topic_id}",
        instrument=None if instrument is None else instrument.strip().lower(),
        min_score=min_score,
        state=state,
        limit=limit,
    )
    return VideosOut(videos=[VideoOut.of(film) for film in found], count=len(found), window_from=start, window_to=end)


async def state(
    conn: Conn,
    settings: Settings,
    providers: Providers,
    *,
    heartbeat=None,
    alerts_configured: bool,
    now: datetime | None = None,
) -> StateOut:
    moment = now or providers.clock.now()
    day = budget.utc_day(moment)
    spent = await store.usage_on(conn, day)
    blocked = await store.provider_states(conn)
    counts = await store.state_counts(conn, since=moment - timedelta(days=RECENT_DAYS))
    channels = await store.list_channels(conn, active_only=True)
    topics = await store.list_topics(conn, active_only=True)

    rows: list[ProviderOut] = []
    for role, ceiling in _ceilings(settings, providers):
        used = spent.get((ceiling.provider, ceiling.unit), 0)
        known = blocked.get(ceiling.provider) if role == "transcripts" else None
        rows.append(
            ProviderOut(
                role=role,  # type: ignore[arg-type]
                name=ceiling.provider,
                unit=ceiling.unit,
                spent_today=used,
                ceiling=ceiling.limit,
                exhausted=used >= ceiling.limit,
                blocked=bool(known and known.blocked),
                blocked_reason=known.blocked_reason if known and known.blocked else None,
                last_blocked_at=known.last_blocked_at if known else None,
            )
        )

    loop = None
    stale = False
    if heartbeat is not None:
        loop = LoopOut(
            ran=heartbeat.has_run,
            age_seconds=heartbeat.age_seconds(),
            expected_seconds=heartbeat.expected_seconds,
            passes_late=heartbeat.passes_late(),
        )
        stale = loop.passes_late > STALE_AFTER_PASSES

    return StateOut(
        day=day,
        simulating=settings.simulating,
        model_configured=providers.analyser is not None,
        alerts_configured=alerts_configured,
        channels_active=len(channels),
        topics_active=len(topics),
        providers=rows,
        waiting=counts.waiting,
        recent=counts.recent,
        recent_days=RECENT_DAYS,
        loop=loop,
        stale=stale,
    )


def _ceilings(settings: Settings, providers: Providers) -> list[tuple[str, budget.Ceiling]]:
    found = budget.ceilings(settings, providers)
    roles = ["source", "transcripts"]
    if providers.analyser is not None:
        roles.append("analyser")
    return list(zip(roles, found, strict=True))
