"""Runs over HTTP: starting one, reading its trace, watching it, interrupting it — and
the property the whole module is built around, that a run is judged against the revision
it started on."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Iterator

import asyncpg
import pytest
from fastapi.testclient import TestClient

from teams import store
from teams.provider import ProviderChunk, TextDelta, UsageReport
from workbench.app import app

from .mcp_stand_in import serving_sync
from .scripted_provider import ScriptedProvider, says
from .write_server import places_orders

pytestmark = pytest.mark.db

MODEL_ID = "gpt-5.6-luna"

_ENV = {
    "TEAMS_OPENAI_API_KEY": "key",
    "TEAMS_MODELS": (
        f'[{{"id":"{MODEL_ID}","model":"luna-prod","display_name":"Luna",'
        '"cost_rank":1,"input_rate_per_1m":"1","output_rate_per_1m":"6"}]'
    ),
}

OWNER = {"X-MS-CLIENT-PRINCIPAL-ID": "operator-1"}
STRANGER = {"X-MS-CLIENT-PRINCIPAL-ID": "operator-2"}


@pytest.fixture(autouse=True)
def _env(workbench_env: None, migrated_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in _ENV.items():
        monkeypatch.setenv(key, value)


@pytest.fixture
def client(db: asyncpg.Connection) -> Iterator[TestClient]:
    """The real app and the real lifespan, with the provider replaced afterwards — the
    routes read it off `app.state` per request, so nothing here needs an OpenAI key to be
    a real one."""
    with TestClient(app) as started:
        app.state.teams.provider = ScriptedProvider(default=says("done."))
        yield started


def _definition(agents: list[dict] | None = None, edges: list[dict] | None = None) -> dict:
    return {
        "agents": agents
        or [
            {
                "key": "scout",
                "role": "scout",
                "prompt": "read the market",
                "model_id": MODEL_ID,
                "tools": [],
            }
        ],
        "edges": edges or [],
    }


def _a_team(client: TestClient, definition: dict | None = None) -> int:
    response = client.post(
        "/teams",
        json={"name": "a team", "description": "", "definition": definition or _definition()},
        headers=OWNER,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _wait_for_status(client: TestClient, run_id: int, wanted: set[str], tries: int = 60) -> dict:
    """Polls the run's own route. Each request hands the loop back to the run's task,
    which is what actually moves it along under `TestClient`."""
    for _ in range(tries):
        run = client.get(f"/runs/{run_id}", headers=OWNER).json()
        if run["status"] in wanted:
            return run
    raise AssertionError(f"run {run_id} never reached {wanted}")


def test_a_run_starts_and_finishes_with_a_trace(client: TestClient) -> None:
    team_id = _a_team(client)

    started = client.post(f"/teams/{team_id}/runs", headers=OWNER)
    assert started.status_code == 201, started.text
    run_id = started.json()["id"]
    assert started.json()["status"] == "pending"

    run = _wait_for_status(client, run_id, {"completed", "failed", "cancelled"})
    assert run["status"] == "completed"
    assert run["finished_at"] is not None

    steps = client.get(f"/runs/{run_id}/steps", headers=OWNER).json()
    assert [step["agent_key"] for step in steps] == ["scout"]
    assert steps[0]["status"] == "completed"
    assert steps[0]["output"] == "done."
    assert client.get(f"/runs/{run_id}/tool-calls", headers=OWNER).json() == []


def test_runs_are_listed_for_their_team_newest_first(client: TestClient) -> None:
    team_id = _a_team(client)
    first = client.post(f"/teams/{team_id}/runs", headers=OWNER).json()["id"]
    _wait_for_status(client, first, {"completed", "failed"})
    second = client.post(f"/teams/{team_id}/runs", headers=OWNER).json()["id"]
    _wait_for_status(client, second, {"completed", "failed"})

    listed = client.get(f"/teams/{team_id}/runs", headers=OWNER).json()

    assert [run["id"] for run in listed] == [second, first]


def test_a_strangers_run_reads_exactly_like_one_that_does_not_exist(client: TestClient) -> None:
    team_id = _a_team(client)
    run_id = client.post(f"/teams/{team_id}/runs", headers=OWNER).json()["id"]
    _wait_for_status(client, run_id, {"completed", "failed"})

    assert client.get(f"/runs/{run_id}", headers=STRANGER).status_code == 404
    assert client.get(f"/runs/{run_id}/steps", headers=STRANGER).status_code == 404
    assert client.get(f"/runs/{run_id}/tool-calls", headers=STRANGER).status_code == 404
    assert client.get(f"/runs/{run_id + 1000}", headers=OWNER).status_code == 404
    assert client.post(f"/teams/{team_id}/runs", headers=STRANGER).status_code == 404


def test_a_revision_naming_a_model_since_withdrawn_cannot_be_run(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """specs/teams-models — the saved revision is checked again at the moment it would
    run, and refused by name rather than quietly answered by another model."""
    team_id = _a_team(client)

    class EmptyCatalogue:
        def ids(self):
            return frozenset()

    monkeypatch.setattr(app.state.teams, "catalogue", EmptyCatalogue())
    response = client.post(f"/teams/{team_id}/runs", headers=OWNER)

    assert response.status_code == 422
    assert "scout" in response.text and MODEL_ID in response.text


class _Sleeper:
    """A provider whose first agent never finishes — for everything that has to reach a
    run while it is still working."""

    def __init__(self) -> None:
        self.entered = asyncio.Event()

    def stream(self, **kwargs) -> AsyncIterator[ProviderChunk]:
        del kwargs

        async def chunks() -> AsyncIterator[ProviderChunk]:
            self.entered.set()
            await asyncio.sleep(30)
            yield TextDelta("never")  # pragma: no cover
            yield UsageReport(None, None, None, None)  # pragma: no cover

        return chunks()


def _start_a_slow_run(client: TestClient) -> tuple[int, int, _Sleeper]:
    team_id = _a_team(client)
    sleeper = _Sleeper()
    app.state.teams.provider = sleeper
    run_id = client.post(f"/teams/{team_id}/runs", headers=OWNER).json()["id"]
    _wait_for_status(client, run_id, {"running"})
    return team_id, run_id, sleeper


def test_saving_a_revision_mid_run_does_not_move_the_run(client: TestClient) -> None:
    """specs/teams-runs, "Definicja zmieniona w trakcie przebiegu" — the property every
    comparison in this module rests on."""
    team_id, run_id, _ = _start_a_slow_run(client)
    before = client.get(f"/runs/{run_id}", headers=OWNER).json()

    saved = client.post(
        f"/teams/{team_id}/revisions",
        json={
            "definition": _definition(
                [
                    {
                        "key": "scout",
                        "role": "scout",
                        "prompt": "completely different instructions",
                        "model_id": MODEL_ID,
                        "tools": [],
                    }
                ]
            )
        },
        headers=OWNER,
    )
    assert saved.status_code == 201, saved.text
    assert saved.json()["version"] == 2

    after = client.get(f"/runs/{run_id}", headers=OWNER).json()
    assert after["team_revision_id"] == before["team_revision_id"]
    # And it is the first revision, not the one just saved.
    assert after["team_revision_id"] != saved.json()["id"]

    client.post(f"/runs/{run_id}/cancel", headers=OWNER)
    _wait_for_status(client, run_id, {"cancelled", "failed"})


def test_an_operator_can_interrupt_a_run(client: TestClient) -> None:
    """specs/teams-runs, "Operator przerywa przebieg w trakcie"."""
    _, run_id, _ = _start_a_slow_run(client)

    cancelled = client.post(f"/runs/{run_id}/cancel", headers=OWNER)
    assert cancelled.status_code == 202

    run = _wait_for_status(client, run_id, {"cancelled"})
    assert "interrupted" in run["stopped_reason"]
    steps = client.get(f"/runs/{run_id}/steps", headers=OWNER).json()
    assert steps[0]["status"] == "failed"


def test_interrupting_a_finished_run_is_refused(client: TestClient) -> None:
    team_id = _a_team(client)
    run_id = client.post(f"/teams/{team_id}/runs", headers=OWNER).json()["id"]
    _wait_for_status(client, run_id, {"completed", "failed"})

    response = client.post(f"/runs/{run_id}/cancel", headers=OWNER)

    assert response.status_code == 409
    assert "already" in response.text


def test_a_strangers_run_cannot_be_interrupted(client: TestClient) -> None:
    _, run_id, _ = _start_a_slow_run(client)

    assert client.post(f"/runs/{run_id}/cancel", headers=STRANGER).status_code == 404

    client.post(f"/runs/{run_id}/cancel", headers=OWNER)
    _wait_for_status(client, run_id, {"cancelled", "failed"})


def test_the_stream_opens_with_where_the_run_is_now(client: TestClient) -> None:
    """specs/teams-runs, "po ponownym otwarciu widać jego bieżący stan" — a viewer that
    arrives after the fact still gets the whole picture, and the stream then closes rather
    than hanging on a run that will never move again."""
    team_id = _a_team(client)
    run_id = client.post(f"/teams/{team_id}/runs", headers=OWNER).json()["id"]
    _wait_for_status(client, run_id, {"completed", "failed"})

    with client.stream("GET", f"/runs/{run_id}/events", headers=OWNER) as stream:
        assert stream.status_code == 200
        body = "".join(stream.iter_text())

    assert "event: snapshot" in body
    payload = json.loads(body.split("data: ", 1)[1].split("\n", 1)[0])
    assert payload["run"]["status"] == "completed"
    assert [step["agent_key"] for step in payload["steps"]] == ["scout"]
    assert payload["steps"][0]["output"] == "done."


def test_a_watcher_is_subscribed_before_the_snapshot_is_read(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reading the snapshot first left a window with no owner: releasing the connection it
    was read on is a suspension point, and an event published there is too late for the
    snapshot and too early for a queue that does not exist yet. A run ending in that window
    left the stream open for ever, because `finished` came off the same stale row.

    The order is what is asserted, not the timing — the window is one turn of the event
    loop and no test can sit inside it."""
    team_id = _a_team(client)
    run_id = client.post(f"/teams/{team_id}/runs", headers=OWNER).json()["id"]
    _wait_for_status(client, run_id, {"completed", "failed"})

    order: list[str] = []
    registry = app.state.teams.runs
    subscribed = registry.subscribe
    read_steps = store.get_run_steps

    def spy_subscribe(watched_run_id: int):
        order.append("subscribe")
        return subscribed(watched_run_id)

    async def spy_get_run_steps(conn, *, run_id: int):
        order.append("snapshot")
        return await read_steps(conn, run_id=run_id)

    monkeypatch.setattr(registry, "subscribe", spy_subscribe)
    monkeypatch.setattr(store, "get_run_steps", spy_get_run_steps)

    with client.stream("GET", f"/runs/{run_id}/events", headers=OWNER) as stream:
        assert stream.status_code == 200
        "".join(stream.iter_text())

    assert order == ["subscribe", "snapshot"]


def test_a_stranger_who_is_refused_leaves_no_watcher_behind(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The price of subscribing first: a queue held over a request that turns out to be a
    404. It is given back, so a refused stranger cannot grow the watcher list of somebody
    else's run."""
    team_id = _a_team(client)
    run_id = client.post(f"/teams/{team_id}/runs", headers=OWNER).json()["id"]
    _wait_for_status(client, run_id, {"completed", "failed"})

    registry = app.state.teams.runs
    with client.stream("GET", f"/runs/{run_id}/events", headers=STRANGER) as stream:
        assert stream.status_code == 404

    # `publish` walks exactly this set; empty is the difference between a queue nobody
    # reads and a queue nobody gave back.
    assert registry._watchers.get(run_id) is None


def test_a_strangers_stream_is_refused(client: TestClient) -> None:
    team_id = _a_team(client)
    run_id = client.post(f"/teams/{team_id}/runs", headers=OWNER).json()["id"]
    _wait_for_status(client, run_id, {"completed", "failed"})

    with client.stream("GET", f"/runs/{run_id}/events", headers=STRANGER) as stream:
        assert stream.status_code == 404


# --- the daily order ceiling (specs/teams-trading) ------------------------------------


@pytest.fixture
def trading_client(db: asyncpg.Connection, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """The app against a stand-in announcing one *write* tool.

    A real announcing server rather than an `app.state.teams.tools` override, because the save
    path does not read `app.state`: it asks whatever servers the settings name
    (`announced_snapshot`), which is what keeps a saved definition checked against what
    is actually published (specs/teams-tool-access).
    """
    with serving_sync(("place_order",)) as url:
        monkeypatch.setenv("TRADING_MCP_URL", url)
        with TestClient(app) as started:
            app.state.teams.provider = ScriptedProvider(default=places_orders(1))
            yield started


def _trading_team(client: TestClient, trading: dict) -> int:
    definition = _definition(
        agents=[
            {
                "key": "trader",
                "role": "trader",
                "prompt": "trade",
                "model_id": MODEL_ID,
                "tools": ["place_order"],
            }
        ]
    )
    definition["trading"] = trading
    return _a_team(client, definition)


def test_a_team_that_used_up_its_daily_orders_is_refused_before_any_agent_runs(
    trading_client: TestClient,
) -> None:
    """specs/teams-trading, "Granica dobowa jest sprawdzana przed utworzeniem przebiegu".
    A run refused halfway is a run that already traded, so the count is read before
    anything is created — and the refusal names the day, not the run."""
    team_id = _trading_team(trading_client, {"orders_per_day": 1})

    first = trading_client.post(f"/teams/{team_id}/runs", headers=OWNER)
    assert first.status_code == 201
    _wait_for_status(trading_client, first.json()["id"], {"completed", "failed"})

    second = trading_client.post(f"/teams/{team_id}/runs", headers=OWNER)

    assert second.status_code == 422
    assert "daily order limit" in second.json()["detail"]
    # Nothing was created for the refused attempt.
    assert len(trading_client.get(f"/teams/{team_id}/runs", headers=OWNER).json()) == 1


def test_a_team_with_no_daily_order_limit_keeps_starting_runs(
    trading_client: TestClient,
) -> None:
    """The operator's own call again: no limit set means none applied, however many
    orders the earlier runs placed."""
    team_id = _trading_team(trading_client, {})

    for _ in range(3):
        started = trading_client.post(f"/teams/{team_id}/runs", headers=OWNER)
        assert started.status_code == 201
        _wait_for_status(trading_client, started.json()["id"], {"completed", "failed"})

    assert len(trading_client.get(f"/teams/{team_id}/runs", headers=OWNER).json()) == 3


def test_the_trades_of_a_run_are_readable_on_their_own_route(
    trading_client: TestClient,
) -> None:
    """specs/teams-trading, "Odczyt zleceń przebiegu". Beside `/tool-calls`, not folded
    into it: that route answers what the agents asked for, this one what happened to the
    account."""
    team_id = _trading_team(trading_client, {})
    run_id = trading_client.post(f"/teams/{team_id}/runs", headers=OWNER).json()["id"]
    _wait_for_status(trading_client, run_id, {"completed", "failed"})

    trades = trading_client.get(f"/runs/{run_id}/trades", headers=OWNER)

    assert trades.status_code == 200
    [trade] = trades.json()
    assert trade["agent_key"] == "trader"
    assert trade["tool_name"] == "place_order"
    assert trade["symbol"] == "GOLD"
    assert trade["direction"] == "BUY"
    # The stand-in answers in prose rather than in trading-mcp's JSON, so the outcome is
    # unknown — and the row says so instead of guessing (specs/teams-trading).
    assert trade["status"] == "unknown"
    assert trade["created_at"] is not None


def test_a_run_that_placed_nothing_has_an_empty_trades_list(client: TestClient) -> None:
    team_id = _a_team(client)
    run_id = client.post(f"/teams/{team_id}/runs", headers=OWNER).json()["id"]
    _wait_for_status(client, run_id, {"completed", "failed"})

    trades = client.get(f"/runs/{run_id}/trades", headers=OWNER)

    assert trades.status_code == 200
    assert trades.json() == []


def test_a_strangers_trades_are_not_readable(client: TestClient) -> None:
    team_id = _a_team(client)
    run_id = client.post(f"/teams/{team_id}/runs", headers=OWNER).json()["id"]
    _wait_for_status(client, run_id, {"completed", "failed"})

    # 404, the same answer as a run that never existed (specs/teams-browser-access).
    assert client.get(f"/runs/{run_id}/trades", headers=STRANGER).status_code == 404
