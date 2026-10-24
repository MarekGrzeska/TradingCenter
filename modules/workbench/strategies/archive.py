"""The candle archive as this package reads it: its REST contract under `/market`, in this process, through the host's
client. The only place here that knows the archive's paths."""

from __future__ import annotations

import httpx

from .vocabulary import Indicator, catalogue_from_wire


class ArchiveUnavailable(Exception):
    """The archive did not answer, or answered with a refusal. Never read as "it holds nothing"."""


class Archive:
    def __init__(self, client: httpx.AsyncClient | None) -> None:
        self._client = client

    async def _get(self, path: str) -> object:
        if self._client is None:
            raise ArchiveUnavailable("the candle archive is not part of this process")
        try:
            response = await self._client.get(path)
        except httpx.HTTPError as err:
            raise ArchiveUnavailable(f"the candle archive did not answer {path}: {type(err).__name__}") from err
        if response.status_code != 200:
            raise ArchiveUnavailable(f"the candle archive refused {path} with {response.status_code}")
        return response.json()

    async def catalogue(self) -> dict[str, Indicator]:
        """`GET /indicators`, read at every check — it is small, and a new entry is then a function at once."""
        answer = await self._get("/indicators")
        assert isinstance(answer, dict)
        return catalogue_from_wire(answer)

    async def tracked(self) -> set[tuple[str, str]]:
        """Every (symbol, resolution) the archive collects."""
        answer = await self._get("/pairs")
        assert isinstance(answer, list)
        return {(pair["symbol"], pair["resolution"]) for pair in answer}
