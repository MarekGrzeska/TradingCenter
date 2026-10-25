"""What the end-to-end stack starts with: US100 tracked on MINUTE with thirty weekdays of a seeded random walk, written
the way the archive writes a history read, a cost profile set as the operator would, and one Telegram recipient. Run in the workbench's project
once its /health answers, so every chain has migrated:

    uv run --project ../workbench python e2e/seed.py
"""

from __future__ import annotations

import asyncio
import random
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import asyncpg
import httpx
from market_data import store, tracking
from market_data.models import Candle, CandleSource, Resolution
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
    async with httpx.AsyncClient(base_url=WORKBENCH) as client:
        (await client.put(f"/strategies/costs/{SYMBOL}", json=COSTS)).raise_for_status()
    print(f"seeded {SYMBOL}: {DAYS} days of minutes to {end:%Y-%m-%d}, cost profile set", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
