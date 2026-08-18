"""`/ping` — the one route that answers with no dependency on anything else."""

from __future__ import annotations

import httpx


async def test_ping_answers_with_no_state_set_up_at_all(app) -> None:
    # No app.state.pool, no app.state.ingest — unlike `/health`, this route MUST NOT
    # touch either, so a request against a bare app (no lifespan run, no db fixture)
    # is exactly the case that proves it.
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://archive.test") as client:
        response = await client.get("/ping")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_ping_reveals_nothing_about_the_archive(app) -> None:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://archive.test") as client:
        body = (await client.get("/ping")).json()

    assert set(body) == {"status"}
