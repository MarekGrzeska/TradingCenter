"""A package mounted whole under a prefix: its routes answer there, the host's stay where they were, and the
state the host fills is the state the package's routes read."""

from __future__ import annotations

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from workbench.assembly import mount_package


def _package() -> FastAPI:
    app = FastAPI()

    @app.get("/health")
    async def health(request: Request) -> dict[str, str]:
        return {"who": "package", "filled": request.app.state.filled}

    return app


def _host() -> FastAPI:
    app = FastAPI()

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"who": "host"}

    return app


def test_the_package_answers_under_its_prefix_and_reads_the_state_the_host_filled() -> None:
    host, package = _host(), _package()
    mount_package(host, "/pkg", package)
    package.state.filled = "by the host"

    with TestClient(host) as client:
        assert client.get("/health").json() == {"who": "host"}
        assert client.get("/pkg/health").json() == {"who": "package", "filled": "by the host"}


def test_a_prefix_is_one_clean_segment() -> None:
    with pytest.raises(ValueError):
        mount_package(_host(), "pkg", _package())
    with pytest.raises(ValueError):
        mount_package(_host(), "/pkg/", _package())
    with pytest.raises(ValueError):
        mount_package(_host(), "/", _package())


def test_a_prefix_is_taken_once() -> None:
    host = _host()
    mount_package(host, "/pkg", _package())

    with pytest.raises(ValueError, match="already mounted"):
        mount_package(host, "/pkg", _package())
