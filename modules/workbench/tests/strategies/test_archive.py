"""The archive's answers as this package reads them: a refusal, silence or a shape it does not know is never read as
"the archive holds nothing"."""

from __future__ import annotations

import httpx
import pytest

from strategies.archive import Archive, ArchiveUnavailable


def archive(handler) -> Archive:
    return Archive(httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://market"))


@pytest.mark.parametrize(
    "response",
    [httpx.Response(503), httpx.Response(200, text="<html>"), httpx.Response(200, json=[{"sym": "US100"}])],
)
async def test_a_refusal_or_an_unreadable_answer_is_unavailability(response) -> None:
    with pytest.raises(ArchiveUnavailable):
        await archive(lambda request: response).tracked()


async def test_the_pairs_are_reused_for_a_while() -> None:
    asked = []

    def handler(request: httpx.Request) -> httpx.Response:
        asked.append(request.url.path)
        return httpx.Response(200, json=[{"symbol": "US100", "resolution": "MINUTE"}])

    reading = archive(handler)
    await reading.tracked()
    assert await reading.tracked() == {("US100", "MINUTE")}
    assert asked == ["/pairs"]
