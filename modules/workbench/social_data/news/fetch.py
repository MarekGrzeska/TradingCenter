"""One GET of one feed, conditional where the feed allows it, answered as a document, as "nothing changed",
or as a failure that says which kind it was."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import httpx

from .feed import Unreadable, items_from
from .models import FeedItem
from .sources import NewsSource

# Larger than any feed measured (Axios, ~1 MB) by a margin; beyond it the answer is not a feed.
MAX_DOCUMENT_BYTES = 5 * 1024 * 1024

_REFUSALS = {401, 403, 429, 451}


class Failure(str, Enum):
    REFUSED = "refused"
    UNREACHABLE = "unreachable"
    UNREADABLE = "unreadable"


class FetchFailed(Exception):
    def __init__(self, kind: Failure, detail: str) -> None:
        super().__init__(f"{kind.value}: {detail}")
        self.kind = kind


@dataclass(frozen=True, slots=True)
class Fetched:
    """`not_modified` is a successful fetch that carried nothing new — the feed answered."""

    items: list[FeedItem] = field(default_factory=list)
    not_modified: bool = False


class FeedClient:
    """Remembers each feed's validators in memory. Losing them on restart costs one full fetch per feed and
    nothing else: no measurement depends on them."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client
        self._validators: dict[str, dict[str, str]] = {}

    async def fetch(self, source: NewsSource) -> Fetched:
        headers = {"Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9"}
        headers.update(self._validators.get(source.id, {}))
        try:
            async with self._client.stream("GET", source.url, headers=headers) as response:
                if response.status_code == 304:
                    return Fetched(not_modified=True)
                if response.status_code in _REFUSALS:
                    raise FetchFailed(Failure.REFUSED, f"HTTP {response.status_code}")
                if not response.is_success:
                    raise FetchFailed(Failure.UNREACHABLE, f"HTTP {response.status_code}")
                # Counted as it arrives: a feed that never ends is refused at the limit, not after it.
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_DOCUMENT_BYTES:
                        raise FetchFailed(
                            Failure.UNREADABLE,
                            f"more than {MAX_DOCUMENT_BYTES} bytes is not a feed",
                        )
                response_headers = response.headers
        except httpx.HTTPError as err:
            raise FetchFailed(Failure.UNREACHABLE, str(err) or type(err).__name__) from err

        try:
            items = items_from(bytes(body), publisher=source.publisher)
        except Unreadable as err:
            raise FetchFailed(Failure.UNREADABLE, str(err)) from err

        # Kept only after a document was read: validators of an answer that failed would turn the next
        # fetch into a "nothing changed" about a document this archive never had.
        validators = {}
        if etag := response_headers.get("ETag"):
            validators["If-None-Match"] = etag
        if modified := response_headers.get("Last-Modified"):
            validators["If-Modified-Since"] = modified
        self._validators[source.id] = validators
        return Fetched(items=items)
