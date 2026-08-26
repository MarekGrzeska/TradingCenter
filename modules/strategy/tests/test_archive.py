"""The archive client, against its contract doubled at the transport. `respx` rather than a fake object,
because what is under test here *is* the reading of the wire."""

from __future__ import annotations

import itertools
import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx

from strategy.archive import Archive, _split
from strategy.catalogue import get
from strategy.errors import ArchiveRefused, ArchiveUnreachable
from strategy.periods import bars_between

BASE = "http://archive.test"
BAR = datetime(2026, 8, 20, 10, 0, tzinfo=UTC)
SPEC = get("baseline_ma_cross")


def client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=BASE)


def indicators_body(**overrides) -> dict:
    body = {
        "symbol": "US100",
        "resolution": "HOUR",
        "price_side": "BID",
        "derived": False,
        "algorithm_version": 1,
        "times": [(BAR - timedelta(hours=1)).isoformat(), BAR.isoformat()],
        "uncovered": [],
        "results": [
            {"id": "ema", "params": {"period": 20}, "settled": True, "lines": {"ema": [99.0, 101.0]}},
            {"id": "ema", "params": {"period": 50}, "settled": True, "lines": {"ema": [100.0, 100.0]}},
            {"id": "atr", "params": {"period": 14}, "settled": True, "lines": {"atr": [2.0, 2.0]}},
        ],
    }
    body.update(overrides)
    return body


def candles_body(count: int = 2) -> dict:
    return {
        "symbol": "US100",
        "resolution": "HOUR",
        "price_side": "BID",
        "derived": False,
        "uncovered": [],
        "candles": [
            {
                "time": (BAR - timedelta(hours=count - 1 - index)).isoformat(),
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.0 + index,
                "volume": None,
            }
            for index in range(count)
        ],
    }


class TestReadingFacts:
    @respx.mock
    async def test_each_fact_comes_back_under_its_own_key(self) -> None:
        """Two facts about `ema` at different periods are the ordinary case, and telling
        them apart is what the key exists for."""
        respx.get(f"{BASE}/candles/US100").mock(return_value=httpx.Response(200, json=candles_body()))
        respx.post(f"{BASE}/indicators/US100").mock(
            return_value=httpx.Response(200, json=indicators_body())
        )

        async with client() as http:
            read = await Archive(BASE, http).read_facts(
                SPEC, "US100", SPEC.resolve_params(), as_of=BAR
            )

        assert set(read.facts.values) == {"fast", "slow", "range"}
        assert read.facts["fast"].last("ema") == 101.0
        assert read.facts["slow"].last("ema") == 100.0
        assert read.facts["range"].last("atr") == 2.0

    @respx.mock
    async def test_the_facts_of_one_resolution_are_asked_for_in_one_request(self) -> None:
        respx.get(f"{BASE}/candles/US100").mock(return_value=httpx.Response(200, json=candles_body()))
        route = respx.post(f"{BASE}/indicators/US100").mock(
            return_value=httpx.Response(200, json=indicators_body())
        )

        async with client() as http:
            await Archive(BASE, http).read_facts(SPEC, "US100", SPEC.resolve_params(), as_of=BAR)

        assert route.call_count == 1
        sent = json.loads(route.calls[0].request.read())
        assert [spec["id"] for spec in sent["specs"]] == ["ema", "ema", "atr"]

    @respx.mock
    async def test_a_period_the_parameters_changed_is_what_gets_asked_for(self) -> None:
        respx.get(f"{BASE}/candles/US100").mock(return_value=httpx.Response(200, json=candles_body()))
        route = respx.post(f"{BASE}/indicators/US100").mock(
            return_value=httpx.Response(200, json=indicators_body())
        )

        async with client() as http:
            await Archive(BASE, http).read_facts(
                SPEC, "US100", SPEC.resolve_params({"fast_period": 8}), as_of=BAR
            )

        # Parsed rather than matched as a substring: what matters is the value asked for,
        # not how json.dumps spaced it. `float` is the archive's own wire type for a
        # parameter — it converts to what an entry needs on its side.
        sent = json.loads(route.calls[0].request.read())
        assert [spec["params"]["period"] for spec in sent["specs"]] == [8.0, 50.0, 14.0]

    @respx.mock
    async def test_an_uncovered_stretch_travels_with_the_answer(self) -> None:
        """The gate that reads this is in `gates.py`; what matters here is that the client
        does not quietly drop it."""
        gap = {"from": (BAR - timedelta(days=2)).isoformat(), "to": (BAR - timedelta(days=1)).isoformat()}
        respx.get(f"{BASE}/candles/US100").mock(return_value=httpx.Response(200, json=candles_body()))
        respx.post(f"{BASE}/indicators/US100").mock(
            return_value=httpx.Response(200, json=indicators_body(uncovered=[gap]))
        )

        async with client() as http:
            read = await Archive(BASE, http).read_facts(
                SPEC, "US100", SPEC.resolve_params(), as_of=BAR
            )

        assert len(read.gaps) == 1
        assert read.gaps[0].end == BAR - timedelta(days=1)

    @respx.mock
    async def test_one_fact_the_archive_could_not_compute_is_carried_not_raised(self) -> None:
        """The other facts were answered, and whether the strategy can decide without this
        one is the strategy's business."""
        body = indicators_body()
        body["results"][2] = {
            "id": "atr",
            "params": {"period": 14},
            "settled": False,
            "error": "no minute series for US100",
        }
        respx.get(f"{BASE}/candles/US100").mock(return_value=httpx.Response(200, json=candles_body()))
        respx.post(f"{BASE}/indicators/US100").mock(return_value=httpx.Response(200, json=body))

        async with client() as http:
            read = await Archive(BASE, http).read_facts(
                SPEC, "US100", SPEC.resolve_params(), as_of=BAR
            )

        assert read.facts["range"].error == "no minute series for US100"
        assert read.facts["fast"].error is None


class TestWhenTheArchiveWillNotAnswer:
    @respx.mock
    async def test_a_connection_failure_is_unreachable(self) -> None:
        respx.get(f"{BASE}/candles/US100").mock(side_effect=httpx.ConnectError("refused"))

        async with client() as http:
            with pytest.raises(ArchiveUnreachable):
                await Archive(BASE, http).read_facts(
                    SPEC, "US100", SPEC.resolve_params(), as_of=BAR
                )

    @respx.mock
    async def test_a_refusal_carries_what_the_archive_said(self) -> None:
        respx.get(f"{BASE}/candles/US100").mock(
            return_value=httpx.Response(422, json={"detail": "the range is reversed"})
        )

        async with client() as http:
            with pytest.raises(ArchiveRefused, match="the range is reversed"):
                await Archive(BASE, http).read_facts(
                    SPEC, "US100", SPEC.resolve_params(), as_of=BAR
                )

    @respx.mock
    async def test_an_answer_in_the_wrong_order_is_refused_rather_than_mapped(self) -> None:
        """A contract across a module boundary, checked rather than trusted: a silent
        mismatch here would hand a strategy one indicator's numbers under another's name."""
        body = indicators_body()
        body["results"][0], body["results"][2] = body["results"][2], body["results"][0]
        respx.get(f"{BASE}/candles/US100").mock(return_value=httpx.Response(200, json=candles_body()))
        respx.post(f"{BASE}/indicators/US100").mock(return_value=httpx.Response(200, json=body))

        async with client() as http:
            with pytest.raises(ArchiveRefused, match="where"):
                await Archive(BASE, http).read_facts(
                    SPEC, "US100", SPEC.resolve_params(), as_of=BAR
                )


class TestTheLastClosedBar:
    @respx.mock
    async def test_it_is_read_from_the_closed_candles_route(self) -> None:
        """The whole of this module's rule about when a period ends: `GET /candles` answers with closed
        bars only, so the last row of a recent window *is* the last closed bar."""
        closed = respx.get(f"{BASE}/candles/US100").mock(
            return_value=httpx.Response(200, json=candles_body())
        )
        forming = respx.get(f"{BASE}/candles/US100/forming").mock(
            return_value=httpx.Response(200, json={})
        )

        async with client() as http:
            bar = await Archive(BASE, http).last_closed_bar("US100", "HOUR")

        assert bar == BAR
        assert closed.called
        assert not forming.called, "the forming candle is for looking at, not for deciding on"

    @respx.mock
    async def test_a_pair_with_no_bars_yet_answers_nothing(self) -> None:
        respx.get(f"{BASE}/candles/US100").mock(
            return_value=httpx.Response(200, json={**candles_body(), "candles": []})
        )

        async with client() as http:
            assert await Archive(BASE, http).last_closed_bar("US100", "HOUR") is None


class TestTheCatalogue:
    @respx.mock
    async def test_the_announced_indicators_are_read_by_id(self) -> None:
        respx.get(f"{BASE}/indicators").mock(
            return_value=httpx.Response(
                200,
                json={"algorithm_version": 1, "indicators": [{"id": "ema"}, {"id": "atr"}]},
            )
        )

        async with client() as http:
            assert await Archive(BASE, http).announced_indicators() == {"ema", "atr"}


class TestSplittingALongRead:
    def test_a_range_within_the_ceiling_is_one_window(self) -> None:
        assert len(_split("HOUR", BAR - timedelta(days=30), BAR)) == 1

    def test_a_range_over_the_ceiling_is_split_and_covered_exactly(self) -> None:
        """The loop never reaches this; the backtest does, over years of minutes. The point
        of it living in the client is that neither the strategy nor the caller has to know
        the ceiling exists."""
        start, end = BAR - timedelta(days=400), BAR
        windows = _split("MINUTE", start, end)

        assert len(windows) > 1
        assert windows[0][0] == start
        assert windows[-1][1] == end
        # No gap and no overlap between neighbours.
        assert all(one[1] == other[0] for one, other in itertools.pairwise(windows))
        assert all(bars_between("MINUTE", *window) <= 200_000 for window in windows)
