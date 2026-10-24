"""The candle archive as this package reads it: its REST contract under `/market`, in this process, through the host's
client. The only place here that knows the archive's paths."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime

import httpx

from .vocabulary import Indicator, catalogue_from_wire


class ArchiveUnavailable(Exception):
    """The archive did not answer, or answered with a refusal. Never read as "it holds nothing"."""


# How long the archive's list of pairs is reused. A model fixing a document asks again every few seconds, and the list
# costs the archive a status query over every pair; a pair added in the terminal is seen within this.
PAIRS_TTL_SECONDS = 60.0


class Archive:
    def __init__(self, client: httpx.AsyncClient | None) -> None:
        self._client = client
        self._tracked: tuple[float, set[tuple[str, str]]] | None = None

    async def _get(self, path: str, params: dict | None = None, body: dict | None = None) -> object:
        if self._client is None:
            raise ArchiveUnavailable("the candle archive is not part of this process")
        try:
            if body is None:
                response = await self._client.get(path, params=params)
            else:
                response = await self._client.post(path, json=body)
        except httpx.HTTPError as err:
            raise ArchiveUnavailable(f"the candle archive did not answer {path}: {type(err).__name__}") from err
        if response.status_code != 200:
            raise ArchiveUnavailable(f"the candle archive refused {path} with {response.status_code}")
        try:
            return response.json()
        except ValueError as err:
            raise ArchiveUnavailable(f"the candle archive answered {path} with something that is not JSON") from err

    async def catalogue(self) -> dict[str, Indicator]:
        """`GET /indicators`, read at every check — it is small, and a new entry is then a function at once."""
        answer = await self._get("/indicators")
        try:
            return catalogue_from_wire(answer)  # type: ignore[arg-type]
        except (AttributeError, KeyError, TypeError, ValueError) as err:
            raise ArchiveUnavailable(f"the archive's catalogue has a shape this package does not read: {err!r}") from err

    async def tracked(self) -> set[tuple[str, str]]:
        """Every (symbol, resolution) the archive collects, reused for `PAIRS_TTL_SECONDS`."""
        now = time.monotonic()
        if self._tracked is not None and now - self._tracked[0] < PAIRS_TTL_SECONDS:
            return self._tracked[1]
        answer = await self._get("/pairs")
        try:
            pairs = {(pair["symbol"], pair["resolution"]) for pair in answer}  # type: ignore[union-attr]
        except (KeyError, TypeError) as err:
            raise ArchiveUnavailable(f"the archive's pairs have a shape this package does not read: {err!r}") from err
        self._tracked = (now, pairs)
        return pairs

    async def check_inputs(self) -> tuple[dict[str, Indicator], set[tuple[str, str]]]:
        """The catalogue and the pairs, asked at once."""
        catalogue, tracked = await asyncio.gather(self.catalogue(), self.tracked())
        return catalogue, tracked

    async def candles(self, symbol: str, resolution: str, start: datetime, end: datetime) -> dict:
        """`GET /candles/{symbol}`: closed candles in `[start, end)` and the stretches the archive never verified."""
        answer = await self._get(
            f"/candles/{symbol}", params={"resolution": resolution, "from": start.isoformat(), "to": end.isoformat()}
        )
        if not isinstance(answer, dict) or not isinstance(answer.get("candles"), list):
            raise ArchiveUnavailable(f"the candle archive's candles for {symbol} have a shape this package does not read")
        return answer

    async def indicator(
        self, symbol: str, resolution: str, start: datetime, end: datetime, id: str, params: dict[str, float]
    ) -> dict:
        """`POST /indicators/{symbol}` for one indicator: its lines on the archive's time axis for `[start, end)`."""
        answer = await self._get(
            f"/indicators/{symbol}",
            body={
                "resolution": resolution, "from": start.isoformat(), "to": end.isoformat(),
                "specs": [{"id": id, "params": params}],
            },
        )
        try:
            result = answer["results"][0]  # type: ignore[index]
            times = answer["times"]  # type: ignore[index]
        except (KeyError, IndexError, TypeError) as err:
            raise ArchiveUnavailable(f"the archive's indicator answer has a shape this package does not read: {err!r}") from err
        if result.get("error"):
            raise ArchiveUnavailable(f"the archive could not compute {id} for {symbol}: {result['error']}")
        return {"times": times, "lines": result.get("lines") or {}, "settled": bool(result.get("settled", True))}
