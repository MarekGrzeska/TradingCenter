"""Telling the alerts package that a run has finished.

A run that ends is news to whoever set up a rule for it — a schedule that failed in the night, a trigger that ran and
spent its limit. The team module does not decide who: it hands over the run, with what a rule can filter by, and the
operator's rules in `/alerts` do the rest.

Done by a sweep rather than at the moment a run closes, for the reason the other producers keep a marker: a process that
is stopped between a run closing and the alerts package answering must still tell it, and a marker in the run's own row is
the only thing that survives that. Latency is the sweep's interval."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg
import httpx

log = logging.getLogger(__name__)

EVENT_TYPE = "teams.run.finished"
EVENT_DESCRIPTION = "A team's run reached its end, whichever way it ended"
EVENT_SCHEMA = {
    "type": "object",
    "properties": {
        "team": {"type": "string", "x-seen-values": True},
        "team_id": {"type": "integer"},
        "run_id": {"type": "integer"},
        "status": {"type": "string", "enum": ["completed", "failed", "cancelled"]},
        "stopped_reason": {"type": "string"},
        "started_by": {"type": "string", "enum": ["operator", "schedule", "trigger"]},
    },
}

# How many runs one sweep tells, how often it looks, and how long a run stays worth telling.
BATCH = 20
SWEEP_SECONDS = 15.0
WINDOW = timedelta(hours=6)
# How long a run the alerts package refused is passed over, so a few refused ones cannot hold up every run behind them.
SULK = timedelta(minutes=10)

_WORDS = {"completed": "zakończony", "failed": "nieudany", "cancelled": "przerwany"}

_UNTOLD = """
    SELECT r.id, r.status, r.stopped_reason, r.finished_at, t.id AS team_id, t.name AS team_name,
           CASE WHEN f.trigger_id IS NOT NULL THEN 'trigger'
                WHEN f.schedule_id IS NOT NULL THEN 'schedule'
                ELSE 'operator' END AS started_by
      FROM runs r
      JOIN team_revisions v ON v.id = r.team_revision_id
      JOIN teams t ON t.id = v.team_id
      LEFT JOIN schedule_fires f ON f.run_id = r.id
     WHERE r.announced_at IS NULL AND r.status IN ('completed', 'failed', 'cancelled') AND r.finished_at >= $1
     ORDER BY r.finished_at
     LIMIT $2
"""


class Rejected(Exception):
    """The alerts package answered, and the answer was no."""


class Unreachable(Exception):
    """The alerts package did not answer at all."""


class Publisher:
    """The two routes this package calls on the alerts package. The client is the host's, over the package's application in
    this process."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def announce(self) -> None:
        body = {"description": EVENT_DESCRIPTION, "schema": EVENT_SCHEMA}
        await self._send("put", f"/event-types/{EVENT_TYPE}", body)

    async def publish(self, *, source_key: str, attributes: dict[str, Any], text: str) -> None:
        await self._send("post", "/events", {"type": EVENT_TYPE, "source_key": source_key, "attributes": attributes, "text": text})

    async def _send(self, verb: str, path: str, body: dict[str, Any]) -> None:
        try:
            response = await getattr(self._client, verb)(path, json=body)
        except httpx.RequestError as err:
            raise Unreachable(f"the alerts package did not answer: {err}") from err
        if response.is_error:
            raise Rejected(f"the alerts package refused {path}: {_detail(response)}")


def _detail(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text.strip() or response.reason_phrase
    detail = body.get("detail") if isinstance(body, dict) else None
    if isinstance(detail, dict):
        return str(detail.get("detail") or detail)
    return str(detail or body)


def message(row: asyncpg.Record) -> str:
    where = {"trigger": "z wyzwalacza", "schedule": "z harmonogramu", "operator": "ręcznie"}[row["started_by"]]
    lines = [f"Zespół „{row['team_name']}” — przebieg {_WORDS[row['status']]} ({where})."]
    if row["stopped_reason"]:
        lines.append(" ".join(str(row["stopped_reason"]).split())[:400])
    return "\n".join(lines)


def attributes_of(row: asyncpg.Record) -> dict[str, Any]:
    return {
        "team": row["team_name"],
        "team_id": row["team_id"],
        "run_id": row["id"],
        "status": row["status"],
        "stopped_reason": row["stopped_reason"] or "",
        "started_by": row["started_by"],
    }


class RunAnnouncer:
    def __init__(self, pool: asyncpg.Pool, publisher: Publisher) -> None:
        self._pool = pool
        self._publisher = publisher
        self._announced = False
        self._task: asyncio.Task[None] | None = None
        # The alerts package last refused the runs. `/state` could say so; for now it is a log line and the next sweep.
        self.failing = False
        self._sulking: dict[int, datetime] = {}

    async def start(self) -> None:
        self._task = asyncio.create_task(self._loop(), name="teams-run-announcer")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def _loop(self) -> None:
        while True:
            try:
                await self.run(datetime.now(UTC))
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("the run announcer could not finish a sweep")
            await asyncio.sleep(SWEEP_SECONDS)

    async def run(self, now: datetime) -> int:
        """How many finished runs were handed over. One failure costs that run its turn and nothing permanent."""
        if not self._announced:
            try:
                await self._publisher.announce()
                self._announced = True
            except (Rejected, Unreachable) as err:
                self.failing = True
                log.info("could not announce %s yet: %s", EVENT_TYPE, err)
                return 0
        self._sulking = {run: until for run, until in self._sulking.items() if until > now}
        async with self._pool.acquire() as conn:
            fetched = await conn.fetch(_UNTOLD, now - WINDOW, BATCH + len(self._sulking))
        waiting = [row for row in fetched if row["id"] not in self._sulking][:BATCH]
        handed = 0
        failed = False
        for row in waiting:
            try:
                await self._publisher.publish(source_key=str(row["id"]), attributes=attributes_of(row), text=message(row))
            except (Rejected, Unreachable) as err:
                log.warning("could not hand over run %s: %s", row["id"], err)
                failed = True
                if isinstance(err, Rejected):
                    self._sulking[row["id"]] = now + SULK
                continue
            async with self._pool.acquire() as conn:
                await conn.execute("UPDATE runs SET announced_at = $2 WHERE id = $1", row["id"], now)
            handed += 1
        self.failing = failed
        return handed


def build(pool: asyncpg.Pool, alerts: httpx.AsyncClient | None) -> RunAnnouncer | None:
    """`None` where there is no alerts package: runs finish and nobody is told, as before."""
    if alerts is None:
        log.info("no alerts package — finished runs will not be announced")
        return None
    return RunAnnouncer(pool, Publisher(alerts))
