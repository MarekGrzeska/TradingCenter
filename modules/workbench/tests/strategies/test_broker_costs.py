"""A cost profile read off the broker (`strategies-backtest`, "Profil kosztów instrumentu pochodzi od brokera"): the
conversion at its own layer, on the demo's recorded numbers, and the first run that needs a profile."""

from __future__ import annotations

import httpx
import pytest

from strategies import costs_store, margins, runs
from strategies.broker_costs import BrokerCostsMissing, from_broker, margin_from_terms
from strategies.config import Settings

from .fake_archive import QUOTE, TERMS, archive_of
from .market import flat, minutes, strategy

MINUTES = minutes(flat(0, 2 * 86400, 100.0))
HITS = [QUOTE | {"symbol": "US100.X", "bid": 1.0, "ask": 9.0}, QUOTE]


def test_the_recorded_answer_becomes_a_cost_model() -> None:
    read = from_broker("US100", HITS, TERMS)

    # The ask minus the bid of the instrument itself, not of the first match.
    assert read.costs.spread == pytest.approx(0.3)
    # capital.com's -0.0151992 % a day on a long is a charge; the short's +0.0069792 % is paid to the holder.
    assert read.costs.overnight_long == pytest.approx(0.000151992)
    assert read.costs.overnight_short == pytest.approx(-0.000069792)
    assert read.costs.rollover_hour == 21 and read.costs.slippage == 0
    assert read.raw["overnight_long_rate"] == -0.0151992 and read.raw["bid"] == 4049.28


@pytest.mark.parametrize(
    ("terms", "named"),
    [
        ({k: v for k, v in TERMS.items() if k != "overnight_long_rate"}, "overnight_long_rate"),
        (TERMS | {"overnight_charge_interval_minutes": 480}, "every 480 minutes"),
        (TERMS | {"overnight_rate_unit": None}, "not as a percentage"),
        (TERMS | {"overnight_charge_at": None}, "overnight_charge_at"),
    ],
)
def test_a_value_the_broker_leaves_out_is_named_never_defaulted(terms: dict, named: str) -> None:
    with pytest.raises(BrokerCostsMissing, match=named):
        from_broker("US100", HITS, terms)


def test_a_search_without_the_instrument_itself_has_no_price() -> None:
    with pytest.raises(BrokerCostsMissing, match="does not list US100"):
        from_broker("US100", HITS[:1], TERMS)


def test_the_brokers_deposit_in_percent_becomes_a_fraction_and_another_unit_is_named() -> None:
    assert margin_from_terms("US100", TERMS).margin_factor == 0.05

    with pytest.raises(BrokerCostsMissing, match="'POINTS'"):
        margin_from_terms("US100", TERMS | {"margin_factor_unit": "POINTS"})


def _client(pool, archive) -> httpx.AsyncClient:
    from strategies.app import create_app

    app = create_app()
    app.state.settings = Settings(database_url="postgresql://localhost/x", _env_file=None)  # type: ignore[call-arg]
    app.state.pool, app.state.archive = pool, archive
    app.state.queue = type("Queue", (), {"wake": lambda self: None, "busy": 0})()
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


RANGE = {"from": "2026-03-02T00:00:00Z", "to": "2026-03-03T00:00:00Z"}


@pytest.mark.db
async def test_the_first_run_without_costs_reads_the_profile_off_the_broker_and_keeps_it(pool) -> None:
    async with _client(pool, archive_of(MINUTES)) as client:
        sid = (await client.post("/strategies", json=strategy())).json()["strategy_id"]
        first = (await client.post("/runs", json={"strategy_id": sid, **RANGE})).json()
        profile = (await client.get("/costs/US100")).json()
        bare = (await client.post("/runs", json={"strategy_id": sid, "without_costs": True, **RANGE})).json()
    async with pool.acquire() as conn:
        made = await runs.get_run(conn, first["id"])
        without = await runs.get_run(conn, bare["id"])

    assert profile["source"] == "broker" and profile["fetched_at"] is not None
    assert profile["broker"]["overnight_short_rate"] == 0.0069792
    assert made is not None and made.request["costs_source"] == "broker"
    assert made.request["costs"] == profile["costs"] and made.request["costs_fetched_at"] is not None
    assert without is not None and without.request["costs_source"] == "none" and without.request["costs"]["spread"] == 0


@pytest.mark.db
async def test_without_financing_the_run_is_refused_and_no_profile_is_made(pool) -> None:
    terms = {k: v for k, v in TERMS.items() if not k.startswith("overnight")}
    async with _client(pool, archive_of(MINUTES, terms=terms)) as client:
        sid = (await client.post("/strategies", json=strategy())).json()["strategy_id"]
        refused = await client.post("/runs", json={"strategy_id": sid, **RANGE})
        profile = await client.get("/costs/US100")
    async with pool.acquire() as conn:
        queued = await conn.fetchval("SELECT count(*) FROM runs")

    assert refused.status_code == 422 and "overnight_long_rate" in refused.json()["problems"][0]["message"]
    assert profile.status_code == 404 and queued == 0


@pytest.mark.db
async def test_a_broker_that_does_not_answer_leaves_the_profile_as_it_was(pool) -> None:
    async with pool.acquire() as conn:
        kept = await costs_store.put_from_broker(conn, "US100", from_broker("US100", HITS, TERMS))
    async with _client(pool, archive_of(MINUTES, broker_answers=False)) as client:
        refused = await client.post("/costs/US100/from-broker")
        after = (await client.get("/costs/US100")).json()

    assert refused.status_code == 503 and "504" in refused.json()["detail"]
    assert after["costs"] == kept.costs.model_dump(mode="json") and after["broker"] == kept.broker


@pytest.mark.db
async def test_the_operators_values_replace_the_brokers_and_the_broker_can_be_asked_again(pool) -> None:
    async with _client(pool, archive_of(MINUTES)) as client:
        typed = (await client.put("/costs/US100", json={
            "spread": 2.0, "slippage": 0.1, "overnight_long": 0.0, "overnight_short": 0.0, "rollover_hour": 22,
        })).json()
        again = (await client.post("/costs/US100/from-broker")).json()

    assert typed["source"] == "operator" and typed["broker"] is None and typed["fetched_at"] is None
    assert again["source"] == "broker" and again["costs"]["rollover_hour"] == 21


BY_DEPOSIT = strategy(sizing={"mode": "margin_fraction", "value": 0.05})


@pytest.mark.db
async def test_the_first_run_sized_by_the_deposit_reads_it_and_leaves_the_cost_profile_alone(pool) -> None:
    async with pool.acquire() as conn:
        kept = await costs_store.put_from_broker(conn, "US100", from_broker("US100", HITS, TERMS))
    async with _client(pool, archive_of(MINUTES)) as client:
        sid = (await client.post("/strategies", json=BY_DEPOSIT)).json()["strategy_id"]
        queued = (await client.post("/runs", json={"strategy_id": sid, **RANGE})).json()
        margin = (await client.get("/margins/US100")).json()
        profile = (await client.get("/costs/US100")).json()
    async with pool.acquire() as conn:
        made = await runs.get_run(conn, queued["id"])

    assert margin["margin_factor"] == 0.05 and margin["source"] == "broker" and margin["broker"]["margin_factor"] == 5.0
    assert profile["costs"] == kept.costs.model_dump(mode="json")
    assert made is not None and made.request["margin_factor"] == 0.05


@pytest.mark.db
async def test_a_deposit_in_an_unknown_unit_refuses_the_run_and_keeps_nothing(pool) -> None:
    async with _client(pool, archive_of(MINUTES, terms=TERMS | {"margin_factor_unit": "POINTS"})) as client:
        sid = (await client.post("/strategies", json=BY_DEPOSIT)).json()["strategy_id"]
        refused = await client.post("/runs", json={"strategy_id": sid, "without_costs": True, **RANGE})
    async with pool.acquire() as conn:
        stored = await margins.get(conn, "US100")

    assert refused.status_code == 422 and "'POINTS'" in refused.json()["problems"][0]["message"] and stored is None


@pytest.mark.db
async def test_a_run_not_sized_by_the_deposit_never_reads_it(pool) -> None:
    terms = {k: v for k, v in TERMS.items() if not k.startswith("margin")}
    async with _client(pool, archive_of(MINUTES, terms=terms)) as client:
        sid = (await client.post("/strategies", json=strategy())).json()["strategy_id"]
        queued = await client.post("/runs", json={"strategy_id": sid, **RANGE})
    async with pool.acquire() as conn:
        stored = await margins.get(conn, "US100")

    assert queued.status_code == 202 and stored is None
