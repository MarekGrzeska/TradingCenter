"""Liveness. The point of these two is what they do *not* touch."""

from __future__ import annotations

import httpx
import pytest


@pytest.fixture
async def api(app):
    """No pool and no upstream on `app.state`: a liveness route that needed either would fail here,
    which is the whole assertion."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://tests") as client:
        yield client


class TestLiveness:
    async def test_the_root_names_this_module(self, api) -> None:
        """`deploy_probe.py` reads this to tell one module from another on the same service plan."""
        response = await api.get("/")

        assert response.status_code == 200
        assert response.json()["service"] == "telegram-gateway"

    async def test_ping_answers_without_a_database_or_an_upstream(self, api) -> None:
        response = await api.get("/ping")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
