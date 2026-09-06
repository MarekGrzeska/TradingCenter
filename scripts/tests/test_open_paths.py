"""Two gates stand in front of every request — Easy Auth's `excluded_paths` and a module's own `OPEN_PATHS` — and a
path is open only if both say so, which the deploy of d2e2290 found the hard way. The other direction is safe."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_SERVICE = REPO_ROOT / "infra" / "app-service.tf"

# `resource "azurerm_linux_web_app" "telegram_gateway"` → modules/telegram-gateway/telegram_gateway/
RESOURCE = re.compile(r'^resource\s+"azurerm_linux_web_app"\s+"([a-z_]+)"\s*\{', re.MULTILINE)
EXCLUDED = re.compile(r"^\s*excluded_paths\s*=\s*\[([^\]]*)\]", re.MULTILINE)
OPEN_PATHS = re.compile(r"^OPEN_PATHS\s*=\s*frozenset\(\{([^}]*)\}\)", re.MULTILINE)


def _strings(raw: str) -> set[str]:
    return set(re.findall(r'"([^"]*)"', raw))


# The workbench serves packages under prefixes, and each keeps a record of its own: a path the app exempts
# under `/market` is open only if `market_data/caller_access.py` opens it *within its mount*. The host's own
# `/health` is a route of the host, which keeps no record — listed so it is not read as a package's.
PACKAGES_UNDER = {
    "workbench": {
        "/market": "market_data",
        "/polymarket": "polymarket_data",
        "/social": "social_data",
        "/strategy": "strategy",
    }
}
HOST_OWN_PATHS = {"workbench": {"/health"}}


def _web_apps() -> list[tuple[str, set[str]]]:
    """Each app's Terraform resource name and the paths it exempts from Easy Auth."""
    text = APP_SERVICE.read_text(encoding="utf-8")
    starts = [(match.group(1), match.start()) for match in RESOURCE.finditer(text)]
    apps = []
    for index, (name, start) in enumerate(starts):
        end = starts[index + 1][1] if index + 1 < len(starts) else len(text)
        excluded = EXCLUDED.search(text, start, end)
        apps.append((name, _strings(excluded.group(1)) if excluded else set()))
    return apps


def _record_in(path: Path) -> set[str] | None:
    if not path.is_file():
        return None
    found = OPEN_PATHS.search(path.read_text(encoding="utf-8"))
    return _strings(found.group(1)) if found else None


def _open_paths(resource_name: str) -> set[str] | None:
    """What the module opens, or `None` if it keeps no record of this shape. `capital-gateway`'s door is the
    shared key checked inside the module, so it is out of scope rather than exempt — and the test below says so.
    A host of packages opens what each package opens, prefixed with its mount, plus its own few paths."""
    if resource_name in PACKAGES_UNDER:
        opened = set(HOST_OWN_PATHS.get(resource_name, set()))
        for prefix, package in PACKAGES_UNDER[resource_name].items():
            record = _record_in(REPO_ROOT / "modules" / resource_name / package / "caller_access.py")
            if record is not None:
                opened |= {f"{prefix}{path}" for path in record}
        return opened
    return _record_in(
        REPO_ROOT / "modules" / resource_name.replace("_", "-") / resource_name / "caller_access.py"
    )


def test_the_apps_are_found_at_all() -> None:
    """A regex that matched nothing would make every test below pass by looking away."""
    names = [name for name, _ in _web_apps()]
    assert len(names) >= 4, names
    assert "workbench" in names and "telegram_gateway" in names


def test_the_modules_that_keep_this_record_still_keep_it() -> None:
    """Stated positively, so the check cannot be satisfied by the record disappearing: if a module stopped
    keeping an `OPEN_PATHS`, the parametrised test below would skip it in silence."""
    keeping = {name for name, _ in _web_apps() if _open_paths(name) is not None}
    assert {"workbench", "telegram_gateway"} <= keeping


@pytest.mark.parametrize("resource_name,excluded", _web_apps(), ids=lambda value: str(value))
def test_every_excluded_path_is_one_the_module_opens(
    resource_name: str, excluded: set[str]
) -> None:
    opened = _open_paths(resource_name)
    if opened is None:
        pytest.skip(f"{resource_name} keeps no per-path caller record")

    unopened = excluded - opened
    assert not unopened, (
        f"{resource_name} excludes {sorted(unopened)} from Easy Auth, and its own "
        f"caller record does not open {'it' if len(unopened) == 1 else 'them'}. A request "
        "to such a path reaches the container and is refused by the module — which reads "
        "as an open path in Terraform and as a 401 to whoever calls it."
    )
