"""Bringing a module's database to the revision its image was built for, at startup under the advisory
lock — so no operator step stands between a merge and a working module.

Alembic is driven through its Python API rather than as a subprocess: the image would otherwise ship the
CLI and resolve `alembic.ini` against a directory App Service picks. Every entry point takes the module's
own migrations directory, which used to be one expression resolving to a different place in each copy."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from alembic import command
from alembic.config import Config

log = logging.getLogger(__name__)


def alembic_config(migrations: Path, database_url: str | None = None) -> Config:
    """A `Config` built in memory rather than read from `alembic.ini`, whose `script_location` is relative.
    `database_url` set here takes the branch for a test's throwaway PostgreSQL; left out, `env.py` reads settings."""
    config = Config()
    config.set_main_option("script_location", str(migrations))
    if database_url is not None:
        config.set_main_option("sqlalchemy.url", database_url)
    return config


def upgrade_to_head(migrations: Path, database_url: str | None = None) -> None:
    """Blocking. `run()` is what a module calls."""
    command.upgrade(alembic_config(migrations, database_url), "head")


async def run(migrations: Path, database_url: str | None = None) -> None:
    """Applies every pending migration, in a worker thread — not for the event loop's sake but because a
    module's `env.py` ends in `asyncio.run(...)`, which raises inside a loop already running."""
    log.info("bringing the database up to the revision this image was built for")
    await asyncio.to_thread(upgrade_to_head, migrations, database_url)
