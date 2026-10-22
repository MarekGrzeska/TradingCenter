"""From a rule going off to a message on the phone — and what is done when it does not arrive.

The door keeps no memory and no queue, so everything about a message that has not arrived is kept here: the fire is written
before the door is asked, it is tried again while a retry still makes sense, and it is let go when it does not. Delivery is at
least once: a crash between Telegram taking a message and this recording it tells the operator twice, which is the cheaper
side of a choice the other side of which is a lost alert."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

import asyncpg

from . import store
from .config import Settings
from .gateway import Gateway

log = logging.getLogger(__name__)

# How many fires one tick takes, and how long a claimed one is left alone before another tick may take it.
BATCH = 20
LEASE_SECONDS = 60
# Where a retry of a fire the door had no answer for starts, doubling to a ceiling.
FIRST_RETRY_SECONDS = 30
LONGEST_RETRY_SECONDS = 900
NO_DOOR = "there is no door to Telegram in this process"


class Deliverer:
    def __init__(self, pool: asyncpg.Pool, settings: Settings, gateway: Gateway | None) -> None:
        self._pool = pool
        self._settings = settings
        self._gateway = gateway

    @property
    def delivering(self) -> bool:
        return self._gateway is not None

    async def run(self, now: datetime) -> int:
        """The fires that are due, sent. Returns how many were taken."""
        async with self._pool.acquire() as conn:
            due = await store.claim_deliveries(conn, now=now, limit=BATCH, lease_seconds=LEASE_SECONDS)
        for row in due:
            try:
                await self._deliver(row, now)
            except Exception:
                # Left leased: it is tried again when the lease runs out, and the log says why it was not this time.
                log.exception("fire %s could not be delivered", row["id"])
        return len(due)

    async def _deliver(self, row: asyncpg.Record, now: datetime) -> None:
        window = timedelta(hours=self._settings.retry_window_hours)
        if now - row["created_at"] > window:
            await self._give_up(row, "abandoned", f"not delivered within {self._settings.retry_window_hours} h, and too late to be news")
            return
        if not row["enabled"]:
            await self._give_up(row, "abandoned", "the rule was switched off before this was sent")
            return
        if self._gateway is None:
            await self._give_up(row, "undeliverable", NO_DOOR)
            return
        if await self._throttled(row, now):
            return

        sent = await self._gateway.send(row["destination"], row["bot"], row["text"])
        async with self._pool.acquire() as conn, conn.transaction():
            if sent.ok:
                await store.settle_fire(conn, row["id"], state="delivered", now=now)
                if row["mode"] == "once":
                    await store.finish_once_rule(conn, row["rule_id"], "fired")
            elif sent.transient:
                wait = sent.retry_after_seconds or min(FIRST_RETRY_SECONDS * 2 ** (row["attempts"] - 1), LONGEST_RETRY_SECONDS)
                await store.retry_fire(conn, row["id"], at=now + timedelta(seconds=wait), reason=sent.reason or "the door asked to wait")
            else:
                await store.settle_fire(conn, row["id"], state="refused", reason=sent.reason)
                await store.reopen_once_rule(conn, row["rule_id"])

    async def _give_up(self, row: asyncpg.Record, state: str, reason: str) -> None:
        async with self._pool.acquire() as conn, conn.transaction():
            await store.settle_fire(conn, row["id"], state=state, reason=reason)
            await store.reopen_once_rule(conn, row["rule_id"])

    async def _throttled(self, row: asyncpg.Record, now: datetime) -> bool:
        """Whether this rule has already told as much as it may this hour. If so the fire is let go, and the operator is
        told once — not once per fire, which would be the flood the cap is there to stop."""
        cap = row["max_per_hour"] or self._settings.max_per_hour
        hour_ago = now - timedelta(hours=1)
        async with self._pool.acquire() as conn:
            told = await store.delivered_since(conn, row["rule_id"], hour_ago)
        if told < cap:
            return False

        async with self._pool.acquire() as conn, conn.transaction():
            await store.settle_fire(conn, row["id"], state="throttled", reason=f"the rule has already told {cap} times in the last hour")
            skipped = await store.throttled_since(conn, row["rule_id"], hour_ago)
        if self._gateway is None:
            return True
        async with self._pool.acquire() as conn:
            mine = await store.claim_throttle_notice(conn, row["rule_id"], now=now, since=hour_ago)
        if mine:
            notice = (
                f"Reguła „{row['rule_name']}” jest zdławiona: wysłała już {cap} wiadomości w ciągu godziny, "
                f"więc kolejne odpalenia są pomijane (do tej pory: {skipped}). Nic z tego nie zostanie wysłane później."
            )
            if not (await self._gateway.send(row["destination"], row["bot"], notice)).ok:
                async with self._pool.acquire() as conn:
                    await store.release_throttle_notice(conn, row["rule_id"])
        return True
