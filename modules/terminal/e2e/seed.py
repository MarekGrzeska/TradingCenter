"""What the end-to-end stack starts with: US100 tracked on MINUTE with thirty weekdays of a seeded random walk, written
the way the archive writes a history read, a cost profile set as the operator would, one Telegram recipient, two social posts, two headlines and two Polymarket events. Run in the workbench's project
once its /health answers, so every chain has migrated:

    uv run --project ../workbench python e2e/seed.py
"""

from __future__ import annotations

import asyncio
import random
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import asyncpg
import httpx
from market_data import store, tracking
from market_data.models import Candle, CandleSource, Resolution
from polymarket_data import store as polymarket
from polymarket_data.models import Event, Market, Outcome, Sample, Surface
from social_data import store as social
from social_data.models import RawPost
from social_data.news import store as news
from social_data.news.models import FeedItem
from telegram_gateway import store as telegram

WORKBENCH = "http://127.0.0.1:18030"
SYMBOL = "US100"
DAYS = 30
COSTS = {"spread": 1.0, "slippage": 0.0, "overnight_long": 0.0001, "overnight_short": 0.0, "rollover_hour": 22}


def database_url(name: str) -> str:
    for line in (Path(__file__).parent / "workbench.env").read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{name}="):
            return line.split("=", 1)[1]
    raise SystemExit(f"workbench.env names no {name}")


def walk(start: datetime, end: datetime) -> list[Candle]:
    rng = random.Random(7)
    price, candles, at = 18_000.0, [], start
    while at < end:
        if at.weekday() < 5:
            close = price + rng.gauss(0, 4)
            high, low = max(price, close) + abs(rng.gauss(0, 2)), min(price, close) - abs(rng.gauss(0, 2))
            candles.append(Candle(symbol=SYMBOL, resolution=Resolution.MINUTE, period_start=at, open=price, high=high,
                                  low=low, close=close, source=CandleSource.HISTORY))
            price = close
        at += timedelta(minutes=1)
    return candles


async def seed_recipient() -> None:
    """One recipient with one bot, so a rule has someone to tell. The token is a placeholder: the Bot API is 127.0.0.1:9."""
    conn = await asyncpg.connect(database_url("TELEGRAM_DATABASE_URL"))
    try:
        bot = await telegram.add_bot(conn, telegram_id=1, username="e2e_bot", title="E2E", token="1:e2e", created_here=False)
        recipient = await telegram.create_recipient(conn, "e2e-operator")
        await telegram.create_destination(conn, recipient=recipient, bot_id=bot.id)
    finally:
        await conn.close()


async def seed_posts() -> None:
    """Two posts of the last hour: one a model scored high, one nobody read."""
    now = datetime.now(UTC)
    conn = await asyncpg.connect(database_url("SOCIAL_DATABASE_URL"))
    try:
        await social.insert_new_posts(conn, [
            RawPost("e2e", "scored", "e2e", "E2E scored post about rates", now - timedelta(minutes=20)),
            RawPost("e2e", "unread", "e2e", "E2E unread post about nothing", now - timedelta(minutes=10)),
        ])
        scored = await social.post_by_external_id(conn, "e2e", "scored")
        assert scored is not None
        await social.save_analysis(conn, scored.id, topics=["rates"], score=9, model="e2e")
        await news.declare_sources(conn, ["aljazeera"])
        await news.insert_items(conn, "aljazeera", [
            FeedItem("alpha", "E2E Hormuz headline", "Al Jazeera", summary="Tankers wait.", published_at=now - timedelta(minutes=30)),
            FeedItem("beta", "E2E Budget headline", "Al Jazeera", summary="Parliament votes.", published_at=now - timedelta(minutes=25)),
        ], seen_at=now - timedelta(minutes=20), previous_fetch_at=None)
    finally:
        await conn.close()


async def seed_events() -> None:
    """Two tracked Polymarket events with one price each, so the list has something to file and something to remove."""
    now = datetime.now(UTC)
    conn = await asyncpg.connect(database_url("POLYMARKET_DATABASE_URL"))
    try:
        for key, price in (("keep", "0.62"), ("drop", "0.31")):
            event = Event(
                f"e2e-{key}", f"e2e-{key}", f"E2E {key} event",
                markets=(Market(f"e2e-{key}-m", f"Will the E2E {key} happen?", (
                    Outcome(0, "Yes", f"e2e-{key}-yes"), Outcome(1, "No", f"e2e-{key}-no"))),),
            )
            event_id = await polymarket.upsert_event(conn, event)
            outcomes = await polymarket.outcome_ids_by_token(conn, event_id)
            await polymarket.record_samples(conn, [
                Sample(outcomes[f"e2e-{key}-yes"], now, Surface.GAMMA, midpoint=Decimal(price)),
                Sample(outcomes[f"e2e-{key}-no"], now, Surface.GAMMA, midpoint=Decimal("1") - Decimal(price)),
            ])
    finally:
        await conn.close()


async def main() -> None:
    end = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    start = end - timedelta(days=DAYS)
    conn = await asyncpg.connect(database_url("MARKET_DATABASE_URL"))
    try:
        await tracking.track(conn, SYMBOL, Resolution.MINUTE, limit=10, collect_from=start)
        async with conn.transaction():
            await store.commit_candles(conn, walk(start, end), symbol=SYMBOL, resolution=Resolution.MINUTE,
                                       covered_from=start, covered_to=end)
    finally:
        await conn.close()
    await seed_recipient()
    await seed_posts()
    await seed_events()
    async with httpx.AsyncClient(base_url=WORKBENCH) as client:
        (await client.put(f"/strategies/costs/{SYMBOL}", json=COSTS)).raise_for_status()
    print(f"seeded {SYMBOL}: {DAYS} days of minutes to {end:%Y-%m-%d}, cost profile set", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
