"""An event comes in, and every rule it satisfies goes off — all in one transaction, so a producer that hears yes knows its
event and what it caused are both there, and one that hears nothing may ask again and get the same yes."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import asyncpg
from jsonschema import Draft202012Validator
from tc_runtime.db import Conn

from . import filtering, store, template
from .contract import EventAccepted, EventIn, FilterTerm
from .rules import source_of


class Unannounced(Exception):
    """Nobody has said an event of this type exists."""


class DoesNotFit(Exception):
    """The event carries what its type's schema says it must not."""


async def publish(conn: Conn, event: EventIn, *, now: datetime) -> EventAccepted:
    schema = await conn.fetchval("SELECT schema FROM event_types WHERE name = $1", event.type)
    if schema is None:
        raise Unannounced(f"nobody has announced an event type {event.type!r}")
    problems = [
        f"{'.'.join(str(part) for part in error.absolute_path) or 'attributes'}: {error.message}"
        for error in Draft202012Validator(store.json_of(schema)).iter_errors(event.attributes)
    ]
    if problems:
        raise DoesNotFit(f"the attributes do not fit {event.type!r}: {'; '.join(problems)}")

    async with conn.transaction():
        event_id, duplicate = await store.insert_event(
            conn,
            type_=event.type,
            source_key=event.source_key,
            attributes=event.attributes,
            text=event.text,
            now=now,
        )
        if duplicate:
            return EventAccepted(id=event_id, duplicate=True, fires=0)
        fires = 0
        for row in await store.event_rules(conn, event.type):
            fires += await _consider(conn, row, event, event_id, now)
    return EventAccepted(id=event_id, duplicate=False, fires=fires)


async def _consider(conn: Conn, row: asyncpg.Record, event: EventIn, event_id: int, now: datetime) -> int:
    source = source_of(row)
    terms: list[FilterTerm] = getattr(source, "filter", [])
    if not filtering.matches(terms, event.attributes):
        return 0
    if row["mode"] == "once" and row["last_fired_at"] is not None:
        # Its one alert is already on its way (or told); the rule is switched off when that is delivered.
        return 0
    cooldown = row["cooldown_seconds"]
    if cooldown and row["last_fired_at"] is not None and (now - row["last_fired_at"]).total_seconds() < cooldown:
        await store.record_check(
            conn,
            row["id"],
            outcome="cooldown",
            reason=f"{event.source_key!r} matched inside the {cooldown} s cool-down of the last alert",
            now=now,
        )
        return 0
    text = template.render(row["template"], _values(row, event))
    return 1 if await store.record_event_fire(conn, row["id"], event_id=event_id, text=text, now=now) else 0


def _values(row: asyncpg.Record, event: EventIn) -> dict[str, Any]:
    """What a message of an event rule can say: the event's own attributes, and over them the three fixed names."""
    return {**event.attributes, "rule": row["name"], "text": event.text, "type": event.type}
