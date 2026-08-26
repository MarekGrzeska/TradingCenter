"""The REST contract: the happy path, one error and one refusal per route. The domain rules are tested
once at the lowest layer that holds them; what is here is that the decision reaches the wire."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import fakes
import pytest

from polymarket_data import changes, parsing, provider, store
from polymarket_data.models import Sample, Surface

pytestmark = pytest.mark.db


async def observe(pool, payload: dict) -> int:
    async with pool.acquire() as conn:
        return await store.upsert_event(conn, parsing.event_from(payload))


async def outcomes_of(pool, event_id: int):
    async with pool.acquire() as conn:
        return await store.outcomes_of_event(conn, event_id)


class TestTracking:
    async def test_an_address_brings_an_event_under_observation(self, api, app, pool) -> None:
        app.state.provider = fakes.FakeProvider(
            by_slug={"an-event": fakes.event_payload()}
        )

        response = await api.post(
            "/events",
            json={"reference": "https://polymarket.com/event/an-event", "group": "tariffs"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["already_tracked"] is False
        assert body["event"]["group"] == "tariffs"
        assert body["event"]["url"] == "https://polymarket.com/event/an-event"
        assert len(body["event"]["markets"][0]["outcomes"]) == 2

    async def test_an_event_the_provider_does_not_have_is_a_404_not_a_failure(
        self, api, app
    ) -> None:
        """"The provider has no such event" tells the operator something; "the provider
        refused" tells the caller to try again."""
        app.state.provider = fakes.FakeProvider(by_slug={})

        response = await api.post("/events", json={"reference": "nope"})

        assert response.status_code == 404
        assert "has no event" in response.json()["detail"]

    async def test_a_provider_refusal_is_a_502_and_says_which_side_failed(
        self, api, app
    ) -> None:
        app.state.provider = fakes.FakeProvider(
            by_slug={"x": provider.ProviderRefused("503 from the provider")}
        )

        response = await api.post("/events", json={"reference": "x"})

        assert response.status_code == 502
        assert "the provider refused" in response.json()["detail"]

    async def test_the_ceiling_refuses_with_what_to_do_first(
        self, api, app, settings
    ) -> None:
        app.state.settings = settings.model_copy(
            update={"max_tracked_events": 1}
        )
        app.state.provider = fakes.FakeProvider(
            by_slug={
                "one": fakes.event_payload("e-1", slug="one"),
                "two": fakes.event_payload("e-2", slug="two", markets=(
                    fakes.market_payload("m-2"),
                )),
            }
        )
        assert (await api.post("/events", json={"reference": "one"})).status_code == 200

        response = await api.post("/events", json={"reference": "two"})

        assert response.status_code == 409
        assert "the operator's to do" in response.json()["detail"]

    async def test_tracking_the_same_event_twice_says_so_rather_than_erring(
        self, api, app
    ) -> None:
        app.state.provider = fakes.FakeProvider(
            by_slug={"an-event": fakes.event_payload()}
        )
        await api.post("/events", json={"reference": "an-event"})

        response = await api.post("/events", json={"reference": "an-event"})

        assert response.status_code == 200
        assert response.json()["already_tracked"] is True

    async def test_removing_an_observation_takes_its_history_with_it(self, api, pool) -> None:
        """The whole of the change: there is no act that leaves one without the other."""
        event_id = await observe(pool, fakes.event_payload())
        outcome_id = (await outcomes_of(pool, event_id))[0][0]
        async with pool.acquire() as conn:
            await store.record_samples(
                conn,
                [Sample(outcome_id=outcome_id, observed_at=_now(),
                        midpoint=Decimal("0.5"), source=Surface.GAMMA)],
            )

        response = await api.delete("/events/e-1")

        assert response.status_code == 204
        assert (await api.get("/events")).json() == []
        # The outcome itself went with the event, so its history is not empty — it is not there.
        # That is the difference between removing an observation and deleting its data.
        history = await api.get(f"/outcomes/{outcome_id}/history")
        assert history.status_code == 404

    async def test_removing_an_observation_that_is_not_running_is_a_404(self, api) -> None:
        assert (await api.delete("/events/never-seen")).status_code == 404

    async def test_there_is_no_way_to_stop_collecting_without_removing(self, app) -> None:
        """Asserted against the published document rather than against one request: a route that no
        longer answers but is still described is still a route somebody writes a client for."""
        paths = app.openapi()["paths"]

        assert "/events/{provider_event_id}/tracking" not in paths
        assert "delete" in paths["/events/{provider_event_id}"]


class TestDeletion:
    async def test_deleting_history_takes_the_collected_ranges_with_it(
        self, api, pool
    ) -> None:
        event_id = await observe(pool, fakes.event_payload())
        outcome_id = (await outcomes_of(pool, event_id))[0][0]
        async with pool.acquire() as conn:
            await store.record_samples(
                conn,
                [Sample(outcome_id=outcome_id, observed_at=_now(),
                        midpoint=Decimal("0.5"), source=Surface.GAMMA)],
            )
            await store.record_collected(conn, outcome_id, _now() - timedelta(hours=1), _now())

        response = await api.delete("/events/e-1/history")

        assert response.status_code == 200
        assert response.json() == {"samples_deleted": 1, "ranges_deleted": 1}

    async def test_deleting_the_history_of_an_unobserved_event_is_a_404(self, api) -> None:
        assert (await api.delete("/events/never-seen/history")).status_code == 404


class TestReads:
    async def test_the_snapshot_is_one_read_over_every_tracked_outcome(
        self, api, pool
    ) -> None:
        event_id = await observe(
            pool,
            fakes.event_payload(
                markets=(
                    fakes.market_payload("m-1"),
                    fakes.market_payload("m-2", outcomes=("A", "B", "C"),
                                         prices=("0.2", "0.3", "0.5")),
                )
            ),
        )
        async with pool.acquire() as conn:
            for outcome_id, _, _ in await store.outcomes_of_event(conn, event_id):
                await store.record_samples(
                    conn,
                    [Sample(outcome_id=outcome_id, observed_at=_now(),
                            midpoint=Decimal("0.5"), source=Surface.GAMMA)],
                )

        body = (await api.get("/snapshot")).json()

        assert len(body["entries"]) == 5
        assert all(entry["price"] == 0.5 for entry in body["entries"])

    async def test_history_names_what_was_actually_collected(self, api, pool) -> None:
        """A gap inside a collected range means nobody traded; the same gap outside one
        means this module was not looking."""
        event_id = await observe(pool, fakes.event_payload())
        outcome_id = (await outcomes_of(pool, event_id))[0][0]
        async with pool.acquire() as conn:
            await store.record_collected(conn, outcome_id, _now() - timedelta(hours=2), _now())

        body = (await api.get(f"/outcomes/{outcome_id}/history")).json()

        assert body["collected_from"] is not None
        assert body["collected_to"] is not None

    async def test_history_of_an_outcome_that_does_not_exist_is_a_404(self, api) -> None:
        assert (await api.get("/outcomes/999999/history")).status_code == 404

    async def test_changes_of_an_unobserved_event_is_a_404(self, api) -> None:
        assert (await api.get("/events/never-seen/changes")).status_code == 404


class TestBackfillStartsOnTracking:
    async def test_tracking_an_event_starts_filling_its_past(self, api, app) -> None:
        """The route answers that the recent past is being filled in, and until this was wired nothing
        kept that promise: `backfill_event` had no caller outside its tests."""
        app.state.provider = fakes.FakeProvider(by_slug={"an-event": fakes.event_payload()})

        answer = await api.post(
            "/events", json={"reference": "https://polymarket.com/event/an-event"}
        )

        assert answer.status_code == 200
        assert len(app.state.ingest.backfilled) == 1

    async def test_tracking_the_same_event_again_reaches_back_for_nothing(
        self, api, app
    ) -> None:
        app.state.provider = fakes.FakeProvider(by_slug={"an-event": fakes.event_payload()})
        body = {"reference": "https://polymarket.com/event/an-event"}
        await api.post("/events", json=body)
        app.state.ingest.backfilled.clear()

        answer = await api.post("/events", json=body)

        assert answer.json()["already_tracked"] is True
        assert app.state.ingest.backfilled == []


class TestWindows:
    async def test_the_answer_carries_exactly_the_windows_the_module_computes(
        self, api, pool
    ) -> None:
        """Read off `changes.WINDOWS` rather than retyped here: a list written out in the test is a second
        place the set lives. What it pins is the shape, not which windows somebody named twice."""
        await observe(pool, fakes.event_payload())

        body = (await api.get("/events/e-1/changes")).json()

        expected = [label for label, _span in changes.WINDOWS]
        assert [w["window"] for w in body["outcomes"][0]["windows"]] == expected

    async def test_a_window_the_history_does_not_reach_is_a_null_with_a_reason(
        self, api, pool
    ) -> None:
        """Never a zero. A zero would be a claim about the market rather than about the
        archive."""
        event_id = await observe(pool, fakes.event_payload())
        outcome_id = (await outcomes_of(pool, event_id))[0][0]
        async with pool.acquire() as conn:
            await store.record_samples(
                conn,
                [Sample(outcome_id=outcome_id, observed_at=_now(),
                        midpoint=Decimal("0.5"), source=Surface.GAMMA)],
            )

        body = (await api.get("/events/e-1/changes")).json()

        seven_days = _window(body["outcomes"][0], "7d")
        assert seven_days["change"] is None
        assert "does not reach back" in seven_days["unavailable"]

    async def test_a_window_with_history_carries_the_moment_it_was_measured_from(
        self, api, pool
    ) -> None:
        """The provider's spacing wobbles and widens on its own, so the base point is rarely
        exactly the window's edge — and the answer says where it actually came from."""
        event_id = await observe(pool, fakes.event_payload())
        outcome_id = (await outcomes_of(pool, event_id))[0][0]
        base_at = _now() - timedelta(hours=1, seconds=20)
        async with pool.acquire() as conn:
            await store.record_samples(
                conn,
                [
                    Sample(outcome_id=outcome_id, observed_at=base_at,
                           midpoint=Decimal("0.4"), source=Surface.GAMMA),
                    Sample(outcome_id=outcome_id, observed_at=_now(),
                           midpoint=Decimal("0.5"), source=Surface.GAMMA),
                ],
            )

        body = (await api.get("/events/e-1/changes")).json()

        one_hour = _window(body["outcomes"][0], "1h")
        assert one_hour["change"] == pytest.approx(0.1)
        assert one_hour["baseline_at"] is not None

    async def test_a_hole_around_the_windows_edge_is_named_rather_than_papered_over(
        self, api, pool
    ) -> None:
        """A base point far older than the window would be a change over a longer window
        than the label says."""
        event_id = await observe(pool, fakes.event_payload())
        outcome_id = (await outcomes_of(pool, event_id))[0][0]
        async with pool.acquire() as conn:
            await store.record_samples(
                conn,
                [
                    Sample(outcome_id=outcome_id, observed_at=_now() - timedelta(hours=20),
                           midpoint=Decimal("0.4"), source=Surface.GAMMA),
                    Sample(outcome_id=outcome_id, observed_at=_now(),
                           midpoint=Decimal("0.5"), source=Surface.GAMMA),
                ],
            )

        body = (await api.get("/events/e-1/changes")).json()

        four_hours = _window(body["outcomes"][0], "4h")
        assert four_hours["change"] is None
        assert "gap in collection" in four_hours["unavailable"]


class TestGroups:
    async def test_the_three_acts_on_a_group(self, api, pool) -> None:
        created = await api.post("/groups", json={"name": "tariffs"})
        assert created.status_code == 201
        group_id = created.json()["id"]

        listed = await api.get("/groups")
        assert [group["name"] for group in listed.json()] == ["tariffs"]

        assert (await api.delete(f"/groups/{group_id}")).status_code == 204

    async def test_deleting_a_group_that_is_not_there_is_a_404(self, api) -> None:
        assert (await api.delete("/groups/424242")).status_code == 404

    async def test_creating_the_same_group_twice_is_not_an_error(self, api) -> None:
        first = await api.post("/groups", json={"name": "tariffs"})
        again = await api.post("/groups", json={"name": "tariffs"})
        assert first.json()["id"] == again.json()["id"]

    async def test_an_empty_name_is_refused_by_the_contract(self, api) -> None:
        assert (await api.post("/groups", json={"name": ""})).status_code == 422


class TestCollectionState:
    async def test_an_observation_nobody_is_collecting_says_so(self, api, pool) -> None:
        """Being on the list does not prove prices are arriving — and an observation nobody
        is collecting looks exactly like a market nobody is trading."""
        await observe(pool, fakes.event_payload())

        body = (await api.get("/events")).json()

        assert body[0]["collection"]["state"] == "stalled"
        assert body[0]["collection"]["reason"]


def _now() -> datetime:
    return datetime.now(UTC)


def _window(outcome: dict, label: str) -> dict:
    return next(window for window in outcome["windows"] if window["window"] == label)
