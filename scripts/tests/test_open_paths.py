"""Two gates stand in front of every request — Easy Auth's `excluded_paths` and a module's own `OPEN_PATHS` — and a
path is open only if both say so, which the deploy of d2e2290 found the hard way. The other direction is safe."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_SERVICE = REPO_ROOT / "infra" / "app-service.tf"

# `resource "azurerm_linux_web_app" "market_data"` → modules/market-data/market_data/
RESOURCE = re.compile(r'^resource\s+"azurerm_linux_web_app"\s+"([a-z_]+)"\s*\{', re.MULTILINE)
EXCLUDED = re.compile(r"^\s*excluded_paths\s*=\s*\[([^\]]*)\]", re.MULTILINE)
OPEN_PATHS = re.compile(r"^OPEN_PATHS\s*=\s*frozenset\(\{([^}]*)\}\)", re.MULTILINE)


def _strings(raw: str) -> set[str]:
    return set(re.findall(r'"([^"]*)"', raw))


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


def _open_paths(resource_name: str) -> set[str] | None:
    """What the module opens, or `None` if it keeps no record of this shape. `capital-gateway`'s door is the
    shared key checked inside the module, so it is out of scope rather than exempt — and the test below says so."""
    path = (
        REPO_ROOT
        / "modules"
        / resource_name.replace("_", "-")
        / resource_name
        / "caller_access.py"
    )
    if not path.is_file():
        return None
    found = OPEN_PATHS.search(path.read_text(encoding="utf-8"))
    return _strings(found.group(1)) if found else None


def test_the_apps_are_found_at_all() -> None:
    """A regex that matched nothing would make every test below pass by looking away."""
    names = [name for name, _ in _web_apps()]
    assert len(names) >= 5, names
    assert "market_data" in names and "strategy" in names


def test_the_modules_that_keep_this_record_still_keep_it() -> None:
    """Stated positively, so the check cannot be satisfied by the record disappearing: if a module stopped
    keeping an `OPEN_PATHS`, the parametrised test below would skip it in silence."""
    keeping = {name for name, _ in _web_apps() if _open_paths(name) is not None}
    assert {"market_data", "strategy"} <= keeping


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
