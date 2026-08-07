"""Shared fixtures — chiefly the throwaway PostgreSQL the `db` tests run against.

A container per test session rather than a shared development database, because the
schema is part of what is under test here. A table left behind by a previous run is
indistinguishable from a migration that works, and that is exactly the failure this
module cannot afford: the archive's correctness *is* its schema.

Docker is not assumed. Without it the `db` tests skip with a reason that says what to
start, instead of failing with a connection error that reads like a bug in the code.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if _docker_is_usable():
        return
    skip = pytest.mark.skip(reason="needs a running Docker daemon for the PostgreSQL container")
    for item in items:
        if "db" in item.keywords:
            item.add_marker(skip)


def _docker_is_usable() -> bool:
    try:
        import docker
    except ImportError:
        return False
    try:
        # A short timeout on purpose. The default waits about a minute for a daemon that
        # is not running, which turns every test run on a machine without Docker into a
        # minute of silence before the same skip. A daemon that cannot answer a ping in
        # two seconds is not one the container fixture would have succeeded against.
        docker.from_env(timeout=2).ping()
    except Exception:  # noqa: BLE001 - any failure here means "no usable daemon"
        return False
    return True


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    """A URL to an empty PostgreSQL, alive for the session and gone afterwards."""
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("postgres:17-alpine", driver=None) as pg:
        yield pg.get_connection_url()
