"""What the operator had set before the alerts package, read from the packages that held it, as the alerts package asks for it.
`alerts` may not import a neighbour, so it describes what it needs (`alerts.legacy.LegacySource`) and the assembly is where
something that fits is built — over the packages' own REST routes, in this process, as this process."""

from __future__ import annotations

import logging

import httpx

from alerts.legacy import Legacy, WatchedChannel, WatchedTopic

log = logging.getLogger(__name__)


class LegacyAlerts:
    def __init__(
        self,
        telegram: httpx.AsyncClient,
        youtube: httpx.AsyncClient | None,
        *,
        youtube_min_score: int,
        social_min_score: int | None,
    ) -> None:
        self._telegram = telegram
        self._youtube = youtube
        self._youtube_min_score = youtube_min_score
        self._social_min_score = social_min_score

    async def read(self) -> Legacy | None:
        """`None` while a neighbour cannot answer yet — they start after the package that asks — so the conversion asks again."""
        assignments = await self._get(self._telegram, "/assignments")
        if assignments is None:
            return None

        channels: list[WatchedChannel] | None = None
        topics: list[WatchedTopic] = []
        if self._youtube is not None:
            found = await self._get(self._youtube, "/channels")
            wanted = await self._get(self._youtube, "/topics")
            if found is None or wanted is None:
                return None
            channels = [WatchedChannel(one["title"], one["alert_rule"], bool(one["active"])) for one in found["channels"]]
            topics = [WatchedTopic(one["phrase"], one["alert_rule"], bool(one["active"])) for one in wanted["topics"]]

        return Legacy(
            assignments={one["key"]: one["destination"] for one in assignments},
            channels=channels,
            topics=topics,
            youtube_min_score=self._youtube_min_score,
            social_min_score=self._social_min_score,
        )

    @staticmethod
    async def _get(client: httpx.AsyncClient, path: str):
        try:
            response = await client.get(path)
        except httpx.RequestError as err:
            log.info("%s is not readable yet: %s", path, err)
            return None
        if response.is_error:
            log.info("%s is not readable yet: HTTP %s", path, response.status_code)
            return None
        return response.json()
