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


async def test_the_traded_minutes_are_read_from_the_range_and_an_unsettled_indicator_is_named() -> None:
    from strategies.document import servable, validate
    from strategies.reading import read

    from .builders import catalogue
    from .market import MONDAY, strategy

    asked: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            asked.append((request.url.path, request.url.params["from"]))
            return httpx.Response(200, json={"candles": [], "uncovered": []})
        return httpx.Response(200, json={"times": [], "results": [{"id": "ema", "settled": False, "lines": {"ema": []}}]})

    document = strategy(entries=[{"side": "long", "when": "close > ema(20)"}])
    checked, _ = validate(document, catalogue(), servable({("US100", "MINUTE")}))
    assert checked is not None

    inputs = await read(archive(handler), checked, {}, catalogue(), MONDAY, MONDAY + 86400)

    minute_from = {start for path, start in asked if path == "/candles/US100" and start.startswith("2026-03-02")}
    assert minute_from == {"2026-03-02T00:00:00+00:00"}
    assert [key.id for key in inputs.unsettled] == ["ema"]
