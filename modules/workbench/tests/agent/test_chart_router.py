"""`GET /chart` — the terminal's half of the chart-control loop.

specs/agent-chart-control, "Konsument czyta tylko to, czego jeszcze nie zastosował".
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agent import store
from agent.app import app
from agent.models import ChartFocus, ChartIndicator

pytestmark = pytest.mark.db

_ENV = {
    "OPENAI_API_KEY": "key",
    "MODELS": (
        '[{"id":"gpt-5.6-luna","model":"luna-prod","display_name":"Luna",'
        '"cost_rank":1,"input_rate_per_1m":"1","output_rate_per_1m":"6"}]'
    ),
    "DEFAULT_MODEL_ID": "gpt-5.6-luna",
}


@pytest.fixture(autouse=True)
def _env(migrated_url: str, db, monkeypatch: pytest.MonkeyPatch) -> None:
    del db  # requested for its TRUNCATE side effect — see test_prompt_router.py's twin
    monkeypatch.setenv("DATABASE_URL", migrated_url)
    for key, value in _ENV.items():
        monkeypatch.setenv(key, value)


async def _command(db, **overrides):
    session = await store.create_session(db, owner_principal="op-1", model_id="gpt-5.6-luna")
    return await store.record_chart_command(
        db,
        session_id=session.id,
        symbol=overrides.get("symbol"),
        resolution=overrides.get("resolution"),
        indicators=overrides.get("indicators"),
        focus=overrides.get("focus"),
    )


def test_an_empty_log_answers_with_nothing() -> None:
    with TestClient(app) as client:
        response = client.get("/chart")

    assert response.status_code == 200
    assert response.json() is None


async def test_a_command_is_published_with_its_sequence(db) -> None:
    written = await _command(
        db,
        symbol="US100",
        resolution="HOUR",
        indicators=[ChartIndicator(id="ema", params={"period": 200}, color="--color-accent")],
    )

    with TestClient(app) as client:
        body = client.get("/chart").json()

    assert body["sequence"] == written.sequence
    assert body["symbol"] == "US100"
    assert body["resolution"] == "HOUR"
    assert body["indicators"] == [
        {"id": "ema", "params": {"period": 200.0}, "color": "--color-accent"}
    ]


async def test_a_focus_is_published_with_its_from_alias(db) -> None:
    written = await _command(
        db,
        symbol="US100",
        focus=ChartFocus(last_bars=100),
    )

    with TestClient(app) as client:
        body = client.get("/chart").json()

    assert body["sequence"] == written.sequence
    assert body["focus"] == {
        "from": None,
        "to": None,
        "around": None,
        "bars": None,
        "last_bars": 100,
    }


async def test_nothing_newer_than_the_cursor_answers_with_nothing(db) -> None:
    written = await _command(db, symbol="US100")

    with TestClient(app) as client:
        first = client.get("/chart", params={"after": written.sequence})
        # Asked twice on purpose: a read that hands a command out once and then forgets
        # it would make a reloaded terminal disagree with a running one.
        second = client.get("/chart", params={"after": written.sequence})

    assert first.json() is None
    assert second.json() is None


async def test_a_consumer_coming_back_gets_everything_it_missed_as_one(db) -> None:
    session = await store.create_session(db, owner_principal="op-1", model_id="gpt-5.6-luna")
    first = await store.record_chart_command(
        db,
        session_id=session.id,
        symbol="US100",
        resolution="MINUTE_5",
        indicators=[ChartIndicator(id="rsi", params={"period": 14})],
        focus=None,
    )
    last = await store.record_chart_command(
        db, session_id=session.id, symbol="GOLD", resolution=None, indicators=None,
        focus=None,
    )

    with TestClient(app) as client:
        body = client.get("/chart", params={"after": first.sequence - 1}).json()

    assert body["sequence"] == last.sequence
    assert body["symbol"] == "GOLD"
    # The later command said nothing about either, so the earlier one still stands.
    assert body["resolution"] == "MINUTE_5"
    assert body["indicators"] == [{"id": "rsi", "params": {"period": 14.0}, "color": None}]


def test_the_route_refuses_an_unauthenticated_request(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REQUIRE_AUTHENTICATED_PRINCIPAL", "true")
    with TestClient(app) as client:
        response = client.get("/chart")

    assert response.status_code == 401
