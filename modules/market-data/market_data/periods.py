"""One instant, two spellings.

`capital-gateway` publishes a candle's period start in two forms, and the split is
deliberate on its side: REST answers with an ISO string because that is what its OpenAPI
schema can describe, the WebSocket answers with epoch seconds because that is what a
charting library indexes by. Its README calls the seam deliberate rather than an
oversight, and for a chart it costs nothing.

For an archive it is a hazard. The same period reached by both roads has to land on the
same key, and a difference of a second — or a zone read off a string that never carried
one — writes a second candle instead of overwriting the first. Nothing else in this
module reads a gateway timestamp; both forms arrive here and leave as one instant.
"""

from __future__ import annotations

from datetime import UTC, datetime


def from_iso(ts: str) -> datetime:
    """A period start as the gateway's REST side spells it.

    The gateway stamps a `Z` onto the provider's `snapshotTimeUTC`, which the provider
    itself omits, so the usual form parses cleanly. A candle the provider gave only a
    broker-local `snapshotTime` for arrives with no zone at all, and that one is read as
    UTC — the same assumption the gateway makes when it parses its own output back, so
    the two modules are wrong together or right together, never quietly apart.
    """
    if not ts or not ts.strip():
        raise ValueError("a candle arrived from the gateway with no timestamp at all")
    try:
        parsed = datetime.fromisoformat(ts)
    except ValueError as err:
        raise ValueError(f"a candle timestamp the gateway sent is unreadable: {ts!r}") from err
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def from_epoch_seconds(seconds: float) -> datetime:
    """A period start as the gateway's stream spells it."""
    return datetime.fromtimestamp(seconds, tz=UTC)


def from_epoch_millis(millis: float) -> datetime:
    """A quote's moment. Milliseconds, because that is what the provider sends and the
    gateway forwards unchanged — the one place the stream does not speak in seconds."""
    return datetime.fromtimestamp(millis / 1000, tz=UTC)
