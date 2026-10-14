"""Two gates stand in front of every request to the workbench — the edge's `EXEMPT_PATHS` (`workbench/edge.py`, what
Easy Auth's `excluded_paths` was) and each package's own `OPEN_PATHS` — and a path is open only if both say so, which
the deploy of d2e2290 found the hard way. The other direction is safe."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
EDGE = REPO_ROOT / "modules" / "workbench" / "workbench" / "edge.py"

EXEMPT = re.compile(r"^EXEMPT_PATHS\s*=\s*frozenset\(\{([^}]*)\}\)", re.MULTILINE)
OPEN_PATHS = re.compile(r"^OPEN_PATHS\s*=\s*frozenset\(\{([^}]*)\}\)", re.MULTILINE)

# The workbench serves packages under prefixes, and each keeps a record of its own: a path the edge exempts under
# `/market` is open only if `market_data/caller_access.py` opens it *within its mount*. The host's own `/health` is a
# route of the host, which keeps no record — listed so it is not read as a package's.
PACKAGES_UNDER = {
    "/market": "market_data",
    "/polymarket": "polymarket_data",
    "/social": "social_data",
    "/strategy": "strategy",
    "/telegram": "telegram_gateway",
}
HOST_OWN_PATHS = {"/health"}


def _strings(raw: str) -> set[str]:
    return set(re.findall(r'"([^"]*)"', raw))


def exempt_at_the_edge() -> set[str]:
    found = EXEMPT.search(EDGE.read_text(encoding="utf-8"))
    assert found, "workbench/edge.py no longer declares EXEMPT_PATHS as a frozenset literal"
    return _strings(found.group(1))


def opened_by_the_records() -> set[str]:
    opened = set(HOST_OWN_PATHS)
    for prefix, package in PACKAGES_UNDER.items():
        record = REPO_ROOT / "modules" / "workbench" / package / "caller_access.py"
        found = OPEN_PATHS.search(record.read_text(encoding="utf-8")) if record.is_file() else None
        if found:
            opened |= {f"{prefix}{path}" for path in _strings(found.group(1))}
    return opened


def test_the_edge_exempts_something_at_all() -> None:
    """A regex that matched nothing would make the test below pass by looking away."""
    assert "/health" in exempt_at_the_edge()


def test_every_path_the_edge_exempts_is_one_a_record_opens() -> None:
    unopened = exempt_at_the_edge() - opened_by_the_records()
    assert not unopened, (
        f"the edge lets {sorted(unopened)} through without a token, and no caller record opens "
        f"{'it' if len(unopened) == 1 else 'them'}: a request reaches the package and is refused there, which reads "
        "as an open path in one file and as a 401 to whoever calls it."
    )
