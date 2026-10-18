"""The logical databases share one PostgreSQL — the one in `deploy/docker-compose.yml` — and every package sizes its own
pool. That makes the numbers one budget nobody was adding up: before this test they came to 64 on paper, held together
only by `min_size=1` and a quiet day.

Two sources are checked, because either alone would let the total through. A package started with no pool setting falls
back to the default in its `config.py`, so the defaults are a budget too; the compose file is what production gets."""

from __future__ import annotations

import pathlib
import re

import pytest
import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
COMPOSE = yaml.safe_load((REPO_ROOT / "deploy" / "docker-compose.yml").read_text(encoding="utf-8"))

# What is left for everything that is not an application pool — the operator's `psql` through a tunnel, a migration
# holding its own connection, the nightly `pg_dump` — is the difference between this and the server's ceiling.
BUDGET = 60

# package -> (config path, the compose setting that sizes it, how many pools that one setting sizes). The workbench's own
# setting sizes two: two schemas, two pools, one process.
MODULES = {
    "workbench/market": ("market_data/config.py", "MARKET_DATABASE_POOL_SIZE", 1),
    "workbench/polymarket": ("polymarket_data/config.py", "POLYMARKET_DATABASE_POOL_SIZE", 1),
    "workbench/social": ("social_data/config.py", "SOCIAL_DATABASE_POOL_SIZE", 1),
    "workbench/telegram": ("telegram_gateway/config.py", "TELEGRAM_DATABASE_POOL_SIZE", 1),
    "workbench/youtube": ("youtube_data/config.py", "YOUTUBE_DATABASE_POOL_SIZE", 1),
    "workbench/alerts": ("alerts/config.py", "ALERTS_DATABASE_POOL_SIZE", 1),
    "workbench": ("workbench/config.py", "DATABASE_POOL_SIZE", 2),
}

DEFAULT = re.compile(r"^\s*database_pool_size:\s*int\s*=\s*(\d+)\s*$", re.MULTILINE)


def declared_default(module: str) -> int:
    path = REPO_ROOT / "modules" / module.split("/")[0] / MODULES[module][0]
    found = DEFAULT.findall(path.read_text(encoding="utf-8"))
    assert len(found) == 1, f"{module}: expected one database_pool_size default, found {found}"
    return int(found[0])


def max_connections() -> int:
    command = COMPOSE["services"]["postgres"]["command"]
    found = [int(part.split("=", 1)[1]) for part in command if str(part).startswith("max_connections=")]
    assert len(found) == 1, "the compose file names max_connections once"
    return found[0]


@pytest.mark.parametrize("module", sorted(MODULES))
def test_every_module_that_owns_a_database_sizes_its_pool(module: str) -> None:
    """Read off `config.py` rather than imported: this job has none of the modules' virtualenvs. A package without the
    setting takes asyncpg's ten."""
    assert declared_default(module) >= 1


def test_the_defaults_come_to_no_more_than_the_budget() -> None:
    shares = {module: declared_default(module) * pools for module, (_, _, pools) in MODULES.items()}
    total = sum(shares.values())
    assert total <= BUDGET, (
        f"the pool defaults come to {total} connections against a budget of {BUDGET}: {shares}. "
        "Lower one before adding another."
    )


def test_production_asks_for_exactly_the_defaults() -> None:
    """The compose file sets each one explicitly, so the budget is readable where the server is. A value apart from a
    package's own default would be a package sized in two places and disagreeing."""
    environment = COMPOSE["services"]["workbench"]["environment"]
    for module, (_, setting, _) in MODULES.items():
        assert setting in environment, f"deploy/docker-compose.yml does not size {module} ({setting})"
        assert int(environment[setting]) == declared_default(module), (
            f"{module} is sized twice and disagrees: {environment[setting]} in the compose file, "
            f"{declared_default(module)} in config.py."
        )


def test_the_budget_leaves_room_for_something_that_is_not_an_application() -> None:
    assert BUDGET < max_connections()
