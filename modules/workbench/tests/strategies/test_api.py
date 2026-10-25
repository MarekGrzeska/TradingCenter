"""The REST contract (`strategies-api`): one test that each state reaches the wire — the rules themselves are tested at
their own layer."""

from __future__ import annotations

import ast
import pathlib

import httpx
import pytest

from strategies import runs
from strategies.archive import Archive
from strategies.caller_access import OPEN_PATHS, REST_PATHS
from strategies.config import Settings

from .builders import run_in_state
from .fake_archive import archive_of
from .market import flat, minutes, strategy, walk
from .test_reports import WALKING, _report

MINUTES = minutes(flat(0, 2 * 86400, 100.0))


def test_the_caller_record_names_exactly_the_routes_the_package_serves() -> None:
    from strategies.app import create_app

    # Read off the published document: routers are attached lazily, so `app.routes` does not list them yet.
    framework = {"/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json"}
    served = set(create_app().openapi()["paths"]) | framework

    assert served == set(REST_PATHS) | set(OPEN_PATHS)


def _client(pool=None, archive: Archive | None = None) -> httpx.AsyncClient:
    from strategies.app import create_app

    app = create_app()
    app.state.settings = Settings(database_url="postgresql://localhost/x", _env_file=None)  # type: ignore[call-arg]
    app.state.pool = pool
    app.state.archive = archive or archive_of(MINUTES)
    app.state.queue = type("Queue", (), {"wake": lambda self: None, "busy": 0})()
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def test_the_language_lists_the_registry_and_the_catalogue() -> None:
    async with _client() as client:
        language = (await client.get("/language")).json()

    assert "crosses_above" in {f["name"] for f in language["functions"]}
    assert {"ema", "bbands"} <= {i["id"] for i in language["indicators"]}
    assert "swing_points" not in {i["id"] for i in language["indicators"]}  # markers are not values


async def test_validate_answers_what_saving_would_and_writes_nothing() -> None:
    async with _client() as client:
        bad = (await client.post("/validate", json=strategy(exits={}))).json()
        good = (await client.post("/validate", json=strategy())).json()
        plain = (await client.post("/validate", json=strategy(exits={"when": "hour == 20"}))).json()

    assert bad["valid"] is False and bad["problems"][0]["path"] == "exits" and bad["summary"] is None
    assert good["valid"] is True and good["problems"] == [] and good["summary"]["name"] == "test"
    assert (bad["execution"], good["execution"], plain["execution"]) == (None, "MINUTE", "HOUR")


async def test_without_the_archive_nothing_is_checked_and_nothing_is_saved() -> None:
    async with _client(archive=Archive(None)) as client:
        response = await client.post("/strategies", json=strategy())

    assert response.status_code == 503


@pytest.mark.db
async def test_a_strategy_is_saved_revised_read_and_archived(pool) -> None:
    async with _client(pool) as client:
        created = (await client.post("/strategies", json=strategy())).json()
        sid = created["strategy_id"]
        revised = (await client.post(f"/strategies/{sid}/revisions", json=strategy(name="second"))).json()
        detail = (await client.get(f"/strategies/{sid}")).json()
        first = (await client.get(f"/strategies/{sid}/revisions/1")).json()
        archived = (await client.post(f"/strategies/{sid}/archive")).json()
        listed = (await client.get("/strategies")).json()

    assert created == {"strategy_id": sid, "revision": 1, "created": True} and revised["revision"] == 2
    assert detail["revision"]["document"]["name"] == "second" and first["document"]["name"] == "test"
    assert archived["archived_at"] is not None and listed == []


@pytest.mark.db
async def test_an_invalid_document_is_refused_with_every_problem_and_leaves_nothing(pool) -> None:
    async with _client(pool) as client:
        response = await client.post("/strategies", json=strategy(symbol="DE40", exits={}))
    async with pool.acquire() as conn:
        count = await conn.fetchval("SELECT count(*) FROM strategies")

    assert response.status_code == 422 and len(response.json()["problems"]) >= 1 and count == 0


@pytest.mark.db
async def test_runs_are_listed_read_and_paged_and_a_missing_one_is_a_404(pool) -> None:
    async with _client(pool) as client:
        sid = (await client.post("/strategies", json=strategy())).json()["strategy_id"]
        body = {"strategy_id": sid, "from": "2026-03-02T00:00:00Z", "to": "2026-03-03T00:00:00Z",
                "costs": {"spread": 1, "slippage": 0, "overnight_long": 0, "overnight_short": 0, "rollover_hour": 22}}
        run_id = (await client.post("/runs", json=body)).json()["id"]
        async with pool.acquire() as conn:
            await conn.execute("UPDATE runs SET status = 'running' WHERE id = $1", run_id)
        trade = {"side": "long", "entry_time": 1772442000, "entry_price": 100.0, "exit_time": 1772445600,
                 "exit_price": 101.0, "units": 1.0, "initial_stop": 90.0, "result_r": 0.1, "result_money": 1.0, "result_pct": 0.0001, "mae_pct": 0.0,
                 "costs": {"spread": 1.0}, "exit_reason": "target", "pessimistic": False}
        await runs.finish(pool, run_id, 1, {"trades": 1}, {"seed": 1}, [trade])
        listed = (await client.get(f"/runs?strategy_id={sid}")).json()
        page = (await client.get(f"/runs/{run_id}/trades")).json()
        health = (await client.get("/health")).json()
        missing = await client.get("/runs/999999")
        too_large = await client.get("/runs/99999999999999999999")

    assert [r["id"] for r in listed] == [run_id] and listed[0]["status"] == "done"
    assert listed[0]["requested_by"] == "operator"
    assert listed[0]["headline"] == {
        "trades": 1, "total_r": None, "expectancy_r": None, "max_drawdown_r": None, "sharpe": None, "return_pct": None,
        "costs_source": "request", "without_costs": False,
    }
    assert page["total"] == 1 and page["trades"][0]["costs"] == {"spread": 1.0}
    assert health == {"database": "reachable", "queue": {"queued": 0, "running": 0}, "max_execution_bars": 1_500_000}
    assert missing.status_code == 404 and too_large.status_code == 422
    assert "report" not in listed[0]


COSTS = {"spread": 1.0, "slippage": 0.1, "overnight_long": 0.0001, "overnight_short": 0.0, "rollover_hour": 22}


@pytest.mark.db
async def test_revisions_are_listed_compared_and_a_stale_base_is_a_conflict(pool) -> None:
    async with _client(pool) as client:
        sid = (await client.post("/strategies", json=strategy())).json()["strategy_id"]
        tighter = strategy(exits={"stop": "entry_price - 1"})
        second = await client.post(f"/strategies/{sid}/revisions?based_on=1", json=tighter)
        stale = await client.post(f"/strategies/{sid}/revisions?based_on=1", json=strategy(name="late"))
        listed = (await client.get(f"/strategies/{sid}/revisions")).json()
        changed = (await client.get(f"/strategies/{sid}/revisions/2/changes")).json()
        first = (await client.get(f"/strategies/{sid}/revisions/1/changes")).json()
        read = (await client.get(f"/strategies/{sid}/revisions/2")).json()

    assert second.json()["revision"] == 2
    assert stale.status_code == 409 and stale.json()["latest_revision"] == 2
    assert [r["n"] for r in listed] == [2, 1] and "document" not in listed[0]
    assert [c["path"] for c in changed["changes"]] == ["exits.stop"] and changed["against"] == 1
    assert first == {"strategy_id": sid, "n": 1, "against": None, "changes": []}
    assert read["summary"]["sections"][0]["title"] == "Instrument" and read["execution"] == "MINUTE"


@pytest.mark.db
async def test_a_cost_profile_is_set_replaced_read_and_refused_when_malformed(pool) -> None:
    async with _client(pool) as client:
        missing = await client.get("/costs/US100")
        await client.put("/costs/US100", json=COSTS)
        replaced = (await client.put("/costs/US100", json=COSTS | {"spread": 2.0})).json()
        malformed = await client.put("/costs/US100", json=COSTS | {"spread": [1.0] * 23})
        listed = (await client.get("/costs")).json()

    assert missing.status_code == 404
    assert replaced["costs"]["spread"] == 2.0 and [p["symbol"] for p in listed] == ["US100"]
    assert malformed.status_code == 422 and listed[0]["costs"]["spread"] == 2.0


@pytest.mark.db
async def test_a_conversation_is_assigned_without_a_revision_or_a_trial(pool) -> None:
    async with _client(pool) as client:
        sid = (await client.post("/strategies", json=strategy())).json()["strategy_id"]
        assigned = (await client.put(f"/strategies/{sid}/conversation", json={"conversation_id": 42})).json()
        detail = (await client.get(f"/strategies/{sid}")).json()
        missing = await client.put("/strategies/999/conversation", json={"conversation_id": 42})

    assert assigned["conversation_id"] == 42 and detail["conversation_id"] == 42
    assert detail["latest_revision"] == 1 and detail["trials"] == 0 and missing.status_code == 404


@pytest.mark.db
async def test_a_report_says_where_its_costs_came_from_and_marks_a_run_without_them(pool) -> None:
    async with _client(pool) as client:
        sid = (await client.post("/strategies", json=strategy())).json()["strategy_id"]
        body = {"strategy_id": sid, "from": "2026-03-02T00:00:00Z", "to": "2026-03-03T00:00:00Z", "without_costs": True}
        run_id = (await client.post("/runs", json=body)).json()["id"]
        async with pool.acquire() as conn:
            await conn.execute("UPDATE runs SET status = 'running' WHERE id = $1", run_id)
        await runs.finish(pool, run_id, 1, _report(WALKING, minutes(walk(10, seed=5))), {"seed": 1}, [])
        report = (await client.get(f"/runs/{run_id}")).json()["report"]
        listed = (await client.get(f"/runs?strategy_id={sid}")).json()

    assert report["without_costs"] is True and report["costs_source"] == "none" and report["costs_fetched_at"] is None
    assert listed[0]["headline"]["without_costs"] is True


@pytest.mark.db
async def test_runs_are_compared_on_the_wire_or_refused_with_the_difference_named(pool) -> None:
    async def finished(client, sid: int, to: str) -> int:
        body = {"strategy_id": sid, "from": "2026-03-02T00:00:00Z", "to": to, "costs": COSTS}
        run_id = (await client.post("/runs", json=body)).json()["id"]
        async with pool.acquire() as conn:
            await conn.execute("UPDATE runs SET status = 'running' WHERE id = $1", run_id)
        await runs.finish(pool, run_id, 1, _report(WALKING, minutes(walk(10, seed=5))), {"seed": 1}, [])
        return run_id

    async with _client(pool) as client:
        first = (await client.post("/strategies", json=strategy())).json()["strategy_id"]
        second = (await client.post("/strategies", json=strategy(name="other"))).json()["strategy_id"]
        a = await finished(client, first, "2026-03-03T00:00:00Z")
        b = await finished(client, second, "2026-03-03T00:00:00Z")
        c = await finished(client, second, "2026-03-04T00:00:00Z")
        compared = await client.get(f"/runs/compare?run_id={b}&run_id={a}")
        refused = await client.get(f"/runs/compare?run_id={a}&run_id={c}")
        alone = await client.get(f"/runs/compare?run_id={a}")
        missing = await client.get(f"/runs/compare?run_id={a}&run_id=999999")

    assert compared.status_code == 200
    assert [(r["run_id"], r["strategy_id"]) for r in compared.json()["runs"]] == [(b, second), (a, first)]
    assert refused.status_code == 422 and f"run {c} covers" in refused.json()["problems"][0]["message"]
    assert alone.status_code == 422 and missing.status_code == 404


@pytest.mark.db
async def test_a_draft_is_read_and_discarded_and_none_is_a_404(pool) -> None:
    from strategies import drafts

    async with pool.acquire() as conn:
        await drafts.put(conn, None, strategy(name="draft"))
    async with _client(pool) as client:
        found = (await client.get("/drafts/new")).json()
        discarded = await client.delete("/drafts/new")
        gone = await client.get("/drafts/new")
        none = await client.get("/strategies/1/draft")

    assert found["document"]["name"] == "draft" and found["strategy_id"] is None and found["seq"] >= 1
    assert discarded.status_code == 204 and gone.status_code == 404 and none.status_code == 404


def test_the_package_has_no_road_to_an_account() -> None:
    """No client, address or setting for trading-mcp or the gateway — read off the source, not trusted to a comment."""
    package = pathlib.Path(__file__).resolve().parents[2] / "strategies"
    text = " ".join(path.read_text(encoding="utf-8") for path in package.rglob("*.py")).lower()
    imported = {
        (node.module or "") if isinstance(node, ast.ImportFrom) else alias.name
        for path in package.rglob("*.py")
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.Import | ast.ImportFrom)
        for alias in node.names
    }

    assert not {m for m in imported if "trading" in m or "gateway" in m or "capital" in m}
    assert "trading_mcp" not in text and "gateway_base_url" not in text
    assert not {name for name in Settings.model_fields if "gateway" in name or "trading" in name}


@pytest.mark.db
async def test_delete_runs_removes_what_is_asked_and_refuses_the_rest_whole(pool) -> None:
    async with _client(pool) as client:
        sid = (await client.post("/strategies", json=strategy())).json()["strategy_id"]
        async with pool.acquire() as conn:
            finished = await run_in_state(conn, sid, "done")
            other = await run_in_state(conn, sid, "failed")
            waiting = await run_in_state(conn, sid, "queued")
        busy = await client.delete(f"/runs?run_id={finished}&run_id={waiting}")
        missing = await client.delete(f"/runs?run_id={finished}&run_id=99999")
        twice = await client.delete(f"/runs?run_id={finished}&run_id={finished}")
        deleted = await client.delete(f"/runs?run_id={finished}&run_id={other}")
        gone = await client.get(f"/runs/{finished}")
        trials = [s["trials"] for s in (await client.get("/strategies")).json()]

    assert busy.status_code == 409 and f"run {waiting} is queued" in busy.text
    assert missing.status_code == 404 and "99999" in missing.text
    assert twice.status_code == 422
    assert deleted.status_code == 200 and deleted.json() == {"deleted": [finished, other]}
    assert gone.status_code == 404 and trials == [1]
