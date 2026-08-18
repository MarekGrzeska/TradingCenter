"""Bringing a module's database to the revision its image was built for.

One copy, taken from three that differed in prose only — `agent`, `teams` and
`market_data` shipped byte-identical code here, measured 18 August 2026 at 83.6–91.8%
including their comments. The container runs this at startup, under `db.advisory_lock`,
so a deployment carries its schema with it and no operator step stands between a merge
and a working module.

Alembic is driven through its Python API rather than as a subprocess. The image would
otherwise have to ship the CLI and resolve `alembic.ini` against a working directory App
Service picks — the same resolution that made agent's last hand-run migration need a copy
of that file with absolute paths in it.

The one thing this package cannot know is where a module keeps its migrations, so every
entry point takes that directory. It used to be `Path(__file__).parent.parent /
"migrations"`, an expression that was identical in all three files and resolved to a
different place in each — which is exactly the kind of difference that becomes an
argument rather than a copy.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from alembic import command
from alembic.config import Config

log = logging.getLogger(__name__)


def alembic_config(migrations: Path, database_url: str | None = None) -> Config:
    """A `Config` built in memory rather than read from `alembic.ini`.

    That file's `script_location` is relative, so reading it would resolve against
    whatever directory the process was started in. `database_url` set here takes the
    branch in a module's `migrations/env.py` that uses the URL verbatim — for a test
    suite's throwaway PostgreSQL. Left out, `env.py` reads the module's own settings and
    connects with its identity, which is the production path.
    """
    config = Config()
    config.set_main_option("script_location", str(migrations))
    if database_url is not None:
        config.set_main_option("sqlalchemy.url", database_url)
    return config


def upgrade_to_head(migrations: Path, database_url: str | None = None) -> None:
    """Blocking. `run()` is what a module calls."""
    command.upgrade(alembic_config(migrations, database_url), "head")


async def run(migrations: Path, database_url: str | None = None) -> None:
    """Applies every pending migration, in a worker thread.

    The thread is not about keeping the event loop responsive — nothing is being served
    yet. It is that a module's `migrations/env.py` ends in `asyncio.run(...)`, which
    raises inside a loop that is already running. A worker thread has no loop of its own,
    so it works there unchanged.
    """
    log.info("bringing the database up to the revision this image was built for")
    await asyncio.to_thread(upgrade_to_head, migrations, database_url)
