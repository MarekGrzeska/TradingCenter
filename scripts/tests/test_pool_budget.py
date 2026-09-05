"""Seven logical databases share one `B_Standard_B1ms` whose `max_connections` is 35, and every module
sizes its own pool. That makes the numbers one budget nobody was adding up: before this test they came
to 64 on paper, held together only by `min_size=1` and a quiet day.

Two sources are checked, because either alone would let the total through. A module deployed with no
`DATABASE_POOL_SIZE` falls back to the default in its `config.py`, so the defaults are a budget too;
Terraform is what production actually gets."""

from __future__ import annotations

import pathlib
import re

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
APP_SERVICE = REPO_ROOT / "infra" / "app-service.tf"

# The server's own ceiling, and what is left for everything that is not an application pool: the
# operator's `psql`, a migration holding its own connection, the platform's own probes. A total at 35
# is a total that fails on the first day two of them coincide.
MAX_CONNECTIONS = 35
BUDGET = 30

# module directory -> (config path, Terraform's resource name, how many pools that one setting sizes).
# The workbench is the only entry above one pool: two schemas, two pools, one process, one setting. The
# three packages joined it, each with a pool of its own, sized by `POLYMARKET_`/`SOCIAL_`/`STRATEGY_DATABASE_POOL_SIZE`.
MODULES = {
    "market-data": ("market_data/config.py", "market_data", 1),
    "workbench/polymarket": ("polymarket_data/config.py", "workbench", 1),
    "workbench/social": ("social_data/config.py", "workbench", 1),
    "workbench/strategy": ("strategy/config.py", "workbench", 1),
    "telegram-gateway": ("telegram_gateway/config.py", "telegram_gateway", 1),
    "workbench": ("workbench/config.py", "workbench", 2),
}

# Where one web app's block starts, so a setting can be read as *that* app's rather than as the
# seventh match in the file.
WEB_APP = re.compile(r'^resource "azurerm_linux_web_app" "(\w+)" \{', re.MULTILINE)

DEFAULT = re.compile(r"^\s*database_pool_size:\s*int\s*=\s*(\d+)\s*$", re.MULTILINE)
# `DATABASE_POOL_SIZE = "8"` in an `app_settings` block, or a package's own `POLYMARKET_DATABASE_POOL_SIZE`.
# Quoted, because every App Service setting is a string however it reads on the other side.
IN_TERRAFORM = re.compile(r'^\s*([A-Z]+_)?DATABASE_POOL_SIZE\s*=\s*"(\d+)"\s*$', re.MULTILINE)


def declared_default(module: str) -> int:
    path = REPO_ROOT / "modules" / module.split("/")[0] / MODULES[module][0]
    found = DEFAULT.findall(path.read_text(encoding="utf-8"))
    assert len(found) == 1, f"{module}: expected one database_pool_size default, found {found}"
    return int(found[0])


@pytest.mark.parametrize("module", sorted(MODULES))
def test_every_module_that_owns_a_database_sizes_its_pool(module: str) -> None:
    """Read off `config.py` rather than imported: six modules, six virtualenvs, and this job has none
    of them. A module without the setting takes asyncpg's ten and spends a third of the server."""
    assert declared_default(module) >= 1


def terraform_settings() -> dict[str, int]:
    """Every pool-size setting per web app, keyed by the app's resource name — and, for a package's own
    pool, by `<app>/<package>` — read out of the block it sits in."""
    text = APP_SERVICE.read_text(encoding="utf-8")
    starts = [(match.group(1), match.start()) for match in WEB_APP.finditer(text)]
    settings: dict[str, int] = {}
    for index, (name, start) in enumerate(starts):
        end = starts[index + 1][1] if index + 1 < len(starts) else len(text)
        for prefix, value in IN_TERRAFORM.findall(text[start:end]):
            key = name if not prefix else f"{name}/{prefix.rstrip('_').lower()}"
            assert key not in settings, f"{key}: more than one pool-size setting"
            settings[key] = int(value)
    return settings


def test_the_defaults_come_to_no_more_than_the_budget() -> None:
    shares = {module: declared_default(module) * pools for module, (_, _, pools) in MODULES.items()}
    total = sum(shares.values())
    assert total <= BUDGET, (
        f"the pool defaults come to {total} connections against a budget of {BUDGET} "
        f"(the server allows {MAX_CONNECTIONS}): {shares}. Lower one before adding another."
    )


def test_production_asks_for_no_more_than_the_defaults_do() -> None:
    """Terraform sets each one explicitly, so the budget is readable where the SKU is. A value above a
    module's own default would be a module sized in two places and disagreeing."""
    in_terraform = terraform_settings()
    expected = {
        resource if "/" not in module else f"{resource}/{module.split('/')[1]}"
        for module, (_, resource, _) in MODULES.items()
    }
    assert set(in_terraform) == expected, (
        f"infra/app-service.tf sets DATABASE_POOL_SIZE for {sorted(in_terraform)}, expected "
        f"{sorted(expected)}. Every module that owns a database names its share there."
    )

    shares = {}
    for module, (_, resource, pools) in MODULES.items():
        key = resource if "/" not in module else f"{resource}/{module.split('/')[1]}"
        value = in_terraform[key]
        default = declared_default(module)
        assert value == default, (
            f"{module} is sized twice and disagrees: {value} in Terraform, {default} in config.py."
        )
        shares[module] = value * pools

    total = sum(shares.values())
    assert total <= BUDGET, (
        f"production asks for {total} connections against a budget of {BUDGET}: {shares}."
    )


def test_the_budget_leaves_room_for_something_that_is_not_an_application() -> None:
    """The operator's `psql`, a migration holding its own connection outside a pool, the platform's
    probes. This is why the budget is not simply `max_connections`."""
    assert BUDGET < MAX_CONNECTIONS
