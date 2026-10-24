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


def archive_of(minute: Series) -> Archive:
    by_resolution = {"MINUTE": minute, "HOUR": hours(minute)}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
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
