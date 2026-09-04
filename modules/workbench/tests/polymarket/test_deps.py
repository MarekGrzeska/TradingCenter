"""What a read does when there is no connection to be had. No database: the pool is the thing
under test, and a real one that is genuinely exhausted is a race dressed up as a fixture."""

from __future__ import annotations

from contextlib import asynccontextmanager

import httpx
import pytest

from polymarket_data.app import create_app


class BusyPool:
    """A pool with nothing free. `acquire` waits out its deadline exactly as asyncpg's does — which is
    what makes `timeout` the only thing standing between a read and the platform's 230 s idle cut."""

    @asynccontextmanager
    async def acquire(self, *, timeout: float | None = None):
        raise TimeoutError(f"no connection came free within {timeout}s")
        yield  # pragma: no cover - unreachable, and required for this to be a generator


@pytest.fixture
async def busy_api(settings):
    app = create_app()
    app.state.pool = BusyPool()
    app.state.settings = settings

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://tests") as client:
        yield client


class TestAReadThatCannotStart:
    async def test_a_busy_archive_refuses_rather_than_hanging(self, busy_api) -> None:
        """503 and not a spinner. A browser sets no deadline of its own, so a read left waiting on
        `acquire()` is a tab that never finishes loading — the symptom this bounds."""
        response = await busy_api.get("/events")

        assert response.status_code == 503
        assert "was not attempted" in response.json()["detail"]

    async def test_the_liveness_route_still_answers(self, busy_api) -> None:
        """`/` reads nothing, and `deploy_probe.py` reads `/`. A module too busy to answer a query
        is not a module that failed to deploy."""
        response = await busy_api.get("/")

        assert response.status_code == 200
        assert response.json()["service"] == "polymarket-data"
