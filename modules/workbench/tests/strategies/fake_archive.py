"""The candle archive's REST contract answered from a minute series in memory — what the queue reads in tests."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx

from strategies.archive import Archive
from strategies.series import Series, epoch

from .builders import CATALOGUE_WIRE
from .market import hours


def _iso(seconds: int) -> str:
    return datetime.fromtimestamp(seconds, tz=UTC).isoformat()


# What the gateway's terms carry for an instrument, as recorded on the demo account for GOLD (design D3).
TERMS = {
    "symbol": "US100", "overnight_long_rate": -0.0151992, "overnight_short_rate": 0.0069792,
    "overnight_rate_unit": "PERCENTAGE", "overnight_charge_at": "2026-07-23T21:00:00Z",
    "overnight_charge_interval_minutes": 1440,
}
QUOTE = {"symbol": "US100", "name": "US Tech 100", "tradeable": True, "bid": 4049.28, "ask": 4049.58}


def archive_of(minute: Series, *, terms: dict | None = None, broker_answers: bool = True) -> Archive:
    """`terms` replaces what the broker says of the instrument; `broker_answers=False` is a gateway that is down."""
    by_resolution = {"MINUTE": minute, "HOUR": hours(minute)}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.startswith("/instruments/") and not broker_answers:
            return httpx.Response(504, json={"detail": "the gateway did not answer"})
        if path == "/instruments/search":
            return httpx.Response(200, json=[QUOTE | {"symbol": "US100.X"}, QUOTE])
        if path == "/instruments/US100/terms":
            return httpx.Response(200, json=TERMS if terms is None else terms)
        if path == "/indicators":
            return httpx.Response(200, json=CATALOGUE_WIRE)
        if path == "/pairs":
            return httpx.Response(200, json=[{"symbol": "US100", "resolution": "MINUTE"}])
        if path == "/candles/US100":
            series = by_resolution[request.url.params["resolution"]]
            lo, hi = epoch(request.url.params["from"]), epoch(request.url.params["to"])
            rows = [
                {"time": _iso(int(s)), **{k: float(series.columns[k][i]) for k in ("open", "high", "low", "close")}}
                for i, s in enumerate(series.starts.tolist()) if lo <= s < hi
            ]
            return httpx.Response(200, json={"candles": rows, "uncovered": []})
        return httpx.Response(404)

    return Archive(httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://market"))
