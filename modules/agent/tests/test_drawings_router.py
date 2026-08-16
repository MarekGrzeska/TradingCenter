"""`/drawings` — the operator's own hand on what the agent drew.

specs/agent-chart-drawings, "Operator cofa rysunek ręką"; specs/terminal-chart,
"Operator zarządza naniesionymi obiektami z listy".
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from agent import store
from agent.app import app
from agent.models import ChartLevel, ChartTrendline, ChartTrendlinePoint, ChartZone

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
    del db  # requested for its TRUNCATE side effect — see test_chart_router.py's twin
    monkeypatch.setenv("DATABASE_URL", migrated_url)
    for key, value in _ENV.items():
        monkeypatch.setenv(key, value)


async def _draw(db, symbol="US100", **kwargs):
    session = await store.create_session(db, owner_principal="op-1", model_id="gpt-5.6-luna")
    geometry = kwargs.pop("geometry", None) or ChartLevel(price=21500.0, label="weekly high")
    [written] = await store.add_drawings(
        db, session_id=session.id, symbol=symbol, geometries=[geometry]
    )
    return written


def test_an_instrument_with_nothing_on_it_answers_with_an_empty_list() -> None:
    with TestClient(app) as client:
        response = client.get("/drawings", params={"symbol": "US100"})

    assert response.status_code == 200
    assert response.json() == []


async def test_a_level_is_published_with_its_geometry(db) -> None:
    written = await _draw(db, geometry=ChartLevel(price=21500.0, label="weekly high"))

    with TestClient(app) as client:
        [published] = client.get("/drawings", params={"symbol": "US100"}).json()

    assert published["id"] == written.id
    assert published["symbol"] == "US100"
    assert published["geometry"] == {"kind": "level", "price": 21500.0, "at": None}
    assert published["label"] == "weekly high"


async def test_a_zone_publishes_its_two_prices_by_name(db) -> None:
    await _draw(db, geometry=ChartZone(top=21600.0, bottom=21550.0))

    with TestClient(app) as client:
        [published] = client.get("/drawings", params={"symbol": "US100"}).json()

    assert published["geometry"]["kind"] == "zone"
    assert published["geometry"]["top"] == 21600.0
    assert published["geometry"]["bottom"] == 21550.0
    # `from` on the wire, not `from_` — the field is named for the reader, not for Python.
    assert "from" in published["geometry"]


async def test_a_trendline_publishes_both_of_its_points(db) -> None:
    await _draw(
        db,
        geometry=ChartTrendline(
            a=ChartTrendlinePoint(time=datetime(2026, 1, 3, tzinfo=UTC), price=21000.0),
            b=ChartTrendlinePoint(time=datetime(2026, 1, 4, tzinfo=UTC), price=21400.0),
        ),
    )

    with TestClient(app) as client:
        [published] = client.get("/drawings", params={"symbol": "US100"}).json()

    assert published["geometry"]["kind"] == "trendline"
    assert published["geometry"]["a"]["price"] == 21000.0
    assert published["geometry"]["b"]["price"] == 21400.0


async def test_the_read_does_not_carry_another_instruments_drawings(db) -> None:
    await _draw(db, symbol="GOLD", geometry=ChartLevel(price=2400.0))
    mine = await _draw(db, symbol="US100")

    with TestClient(app) as client:
        published = client.get("/drawings", params={"symbol": "US100"}).json()

    assert [entry["id"] for entry in published] == [mine.id]


async def test_a_correction_keeps_the_drawing_s_identity(db) -> None:
    written = await _draw(db)

    with TestClient(app) as client:
        response = client.patch(
            f"/drawings/{written.id}", json={"price": 21550.0, "label": "moved up"}
        )

    assert response.status_code == 200
    corrected = response.json()
    assert corrected["id"] == written.id
    assert corrected["symbol"] == "US100"
    assert corrected["geometry"] == {"kind": "level", "price": 21550.0, "at": None}
    assert corrected["label"] == "moved up"


async def test_a_correction_of_one_field_leaves_the_other(db) -> None:
    written = await _draw(db)

    with TestClient(app) as client:
        corrected = client.patch(f"/drawings/{written.id}", json={"label": "renamed"}).json()

    assert corrected["geometry"]["price"] == 21500.0
    assert corrected["label"] == "renamed"


async def test_a_zone_s_upper_price_alone_is_checked_against_the_lower_it_has(db) -> None:
    written = await _draw(db, geometry=ChartZone(top=21600.0, bottom=21550.0))

    with TestClient(app) as client:
        response = client.patch(f"/drawings/{written.id}", json={"top": 21500.0})

    assert response.status_code == 422
    [standing] = await store.list_drawings(db, symbol="US100")
    assert standing.geometry.top == 21600.0  # pyright: ignore[reportAttributeAccessIssue]


async def test_a_price_role_the_shape_does_not_have_is_refused(db) -> None:
    written = await _draw(db)  # a level

    with TestClient(app) as client:
        response = client.patch(f"/drawings/{written.id}", json={"top": 21600.0})

    assert response.status_code == 422
    assert "level" in response.json()["detail"]


async def test_a_request_that_changes_nothing_is_refused(db) -> None:
    written = await _draw(db)

    with TestClient(app) as client:
        assert client.patch(f"/drawings/{written.id}", json={}).status_code == 422


async def test_correcting_a_drawing_that_is_not_there_is_a_404(db) -> None:
    written = await _draw(db)

    with TestClient(app) as client:
        response = client.patch(f"/drawings/{written.id + 99}", json={"price": 1.0})

    assert response.status_code == 404


async def test_a_removal_is_lasting(db) -> None:
    written = await _draw(db)

    with TestClient(app) as client:
        assert client.delete(f"/drawings/{written.id}").status_code == 204
        assert client.get("/drawings", params={"symbol": "US100"}).json() == []

    assert await store.list_drawings(db, symbol="US100") == []


async def test_removing_a_drawing_that_is_not_there_is_a_404_not_a_quiet_success(db) -> None:
    written = await _draw(db)

    with TestClient(app) as client:
        response = client.delete(f"/drawings/{written.id + 99}")

    assert response.status_code == 404
    assert len(await store.list_drawings(db, symbol="US100")) == 1


async def test_a_correction_is_what_the_model_reads_back(db) -> None:
    """The id the model held before the operator moved the level still points at it
    (specs/agent-chart-drawings, "Operator poprawia cenę poziomu")."""
    written = await _draw(db)

    with TestClient(app) as client:
        client.patch(f"/drawings/{written.id}", json={"price": 21550.0})

    [standing] = await store.list_drawings(db, symbol="US100")
    assert standing.id == written.id
    assert standing.geometry.price == 21550.0  # pyright: ignore[reportAttributeAccessIssue]


async def test_a_drawing_is_published_as_lit_until_it_is_hidden(db) -> None:
    await _draw(db)

    with TestClient(app) as client:
        [published] = client.get("/drawings", params={"symbol": "US100"}).json()

    assert published["hidden"] is False


async def test_the_operator_hides_a_drawing_and_shows_it_again(db) -> None:
    """specs/terminal-chart, "Operator gasi poziom z listy" — hiding travels the same
    route a price correction does, because it is a correction of the drawing like any
    other (design.md, "Operator gasi przez `PATCH /drawings/{id}`")."""
    written = await _draw(db)

    with TestClient(app) as client:
        hidden = client.patch(f"/drawings/{written.id}", json={"hidden": True})
        [after_hiding] = client.get("/drawings", params={"symbol": "US100"}).json()
        shown = client.patch(f"/drawings/{written.id}", json={"hidden": False})

    assert hidden.status_code == 200
    assert hidden.json()["hidden"] is True
    assert after_hiding["hidden"] is True
    # And back, unchanged in every other way.
    assert shown.json()["hidden"] is False
    assert shown.json()["geometry"] == {"kind": "level", "price": 21500.0, "at": None}
    assert shown.json()["label"] == "weekly high"


async def test_hiding_alone_counts_as_a_change(db) -> None:
    # `{}` is refused as "this request changes nothing"; `{"hidden": true}` must not fall
    # into the same bucket now that it is a field of its own.
    written = await _draw(db)

    with TestClient(app) as client:
        response = client.patch(f"/drawings/{written.id}", json={"hidden": True})

    assert response.status_code == 200


async def test_a_correction_says_nothing_about_visibility_unless_asked(db) -> None:
    written = await _draw(db)

    with TestClient(app) as client:
        client.patch(f"/drawings/{written.id}", json={"hidden": True})
        corrected = client.patch(f"/drawings/{written.id}", json={"price": 21550.0}).json()

    assert corrected["geometry"]["price"] == 21550.0
    assert corrected["hidden"] is True


async def test_hiding_a_drawing_that_is_not_there_is_a_404(db) -> None:
    written = await _draw(db)

    with TestClient(app) as client:
        response = client.patch(f"/drawings/{written.id + 99}", json={"hidden": True})

    assert response.status_code == 404
