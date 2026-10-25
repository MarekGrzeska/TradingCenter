"""What the end-to-end stack starts with: US100 tracked on MINUTE with thirty weekdays of a seeded random walk, written
the way the archive writes a history read, and a cost profile set as the operator would. Run in the workbench's project
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

WORKBENCH = "http://127.0.0.1:18030"
SYMBOL = "US100"
DAYS = 30
COSTS = {"spread": 1.0, "slippage": 0.0, "overnight_long": 0.0001, "overnight_short": 0.0, "rollover_hour": 22}


def market_url() -> str:
    for line in (Path(__file__).parent / "workbench.env").read_text(encoding="utf-8").splitlines():
        if line.startswith("MARKET_DATABASE_URL="):
            return line.split("=", 1)[1]
    raise SystemExit("workbench.env names no MARKET_DATABASE_URL")


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


async def main() -> None:
    end = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    start = end - timedelta(days=DAYS)
    conn = await asyncpg.connect(market_url())
    try:
        await tracking.track(conn, SYMBOL, Resolution.MINUTE, limit=10, collect_from=start)
        async with conn.transaction():
            await store.commit_candles(conn, walk(start, end), symbol=SYMBOL, resolution=Resolution.MINUTE,
                                       covered_from=start, covered_to=end)
    finally:
        await conn.close()
    async with httpx.AsyncClient(base_url=WORKBENCH) as client:
        (await client.put(f"/strategies/costs/{SYMBOL}", json=COSTS)).raise_for_status()
    print(f"seeded {SYMBOL}: {DAYS} days of minutes to {end:%Y-%m-%d}, cost profile set", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
