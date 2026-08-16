"""Bringing this module's database to the revision its image was built for.

A twin of `agent/migrate.py`, duplicated rather than shared — no library between
modules. The container runs this at startup (`app.py`), under the advisory lock in
`db.py`, so a deployment carries its schema with it and no operator step stands between
a merge and a working module (`teams-database-connection`, "Moduł sam doprowadza bazę do
rewizji, dla której powstał").

Alembic is driven through its Python API rather than as a subprocess. The image would
otherwise have to ship the CLI and resolve `alembic.ini` against a working directory App
Service picks — the same resolution that made agent's last hand-run migration need a
copy of that file with absolute paths in it.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from alembic import command
from alembic.config import Config

log = logging.getLogger(__name__)

# `teams/` and `migrations/` are siblings — in the repository and in the image
# (`Dockerfile` copies both to `/app`), so one expression locates it in both.
MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"


def alembic_config(database_url: str | None = None) -> Config:
    """A `Config` built in memory rather than read from `alembic.ini`.

    That file's `script_location` is relative, so reading it would resolve against
    whatever directory the process was started in. `database_url` set here takes the
    branch in `migrations/env.py` that uses the URL verbatim — for the test suite's
    throwaway PostgreSQL. Left out, `env.py` reads the module's own settings and
    connects with its identity, which is the production path.
    """
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS))
    if database_url is not None:
        config.set_main_option("sqlalchemy.url", database_url)
    return config


def upgrade_to_head(database_url: str | None = None) -> None:
    """Blocking. `run()` is what the module calls."""
    command.upgrade(alembic_config(database_url), "head")


async def run(database_url: str | None = None) -> None:
    """Applies every pending migration, in a worker thread.

    The thread is not about keeping the event loop responsive — nothing is being served
    yet. It is that `migrations/env.py` ends in `asyncio.run(...)`, which raises inside a
    loop that is already running. A worker thread has no loop of its own, so it works
    there unchanged.
    """
    log.info("bringing the database up to the revision this image was built for")
    await asyncio.to_thread(upgrade_to_head, database_url)
