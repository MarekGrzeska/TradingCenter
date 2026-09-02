#!/usr/bin/env python3
"""How much of the Python here is a hand-maintained copy of other Python here — the number condition 1 of
`docs/architecture.md`'s sharing rule rests on, taken per pair of modules holding a file of the same name by
`difflib.SequenceMatcher` with `autojunk` off. Comments count: prose kept in step is a copy too.

    uv run --no-project python scripts/measure-duplication.py --threshold 40
"""
from __future__ import annotations

import argparse
import difflib
import itertools
import pathlib
import sys
from collections import defaultdict

REPO = pathlib.Path(__file__).resolve().parent.parent

# label -> the package's path under `modules/`. Explicit rather than globbed, so a new module is a
# line here — and `test_measure_duplication.py` fails when it is not, because this list naming three
# deleted modules and none of the four newest is how the measurement read zero for twelve days.
# The workbench contributes three: its packages may not import each other, so they copy like modules.
MODULES = {
    "capital-gateway": "capital-gateway/capital_gateway",
    "market-data": "market-data/market_data",
    "polymarket-data": "polymarket-data/polymarket_data",
    "social-data": "social-data/social_data",
    "strategy": "strategy/strategy",
    "telegram-gateway": "telegram-gateway/telegram_gateway",
    "trading-mcp": "trading-mcp/trading_mcp",
    "workbench:agent": "workbench/agent",
    "workbench:teams": "workbench/teams",
    "workbench:teams_tools": "workbench/teams_tools",
    "workbench": "workbench/workbench",
}


def identity(a: pathlib.Path, b: pathlib.Path) -> tuple[float, int]:
    """Percentage of lines in common, and how many lines that is."""
    left = a.read_text(encoding="utf-8").splitlines()
    right = b.read_text(encoding="utf-8").splitlines()
    matcher = difflib.SequenceMatcher(None, left, right, autojunk=False)
    common = sum(block.size for block in matcher.get_matching_blocks())
    return 100 * common / max(len(left), len(right)), common


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--threshold",
        type=float,
        default=40.0,
        help="report pairs at or above this percentage (default: 40)",
    )
    parser.add_argument(
        "--twin-at",
        type=float,
        default=70.0,
        help="the percentage that counts as a twin for the total (default: 70)",
    )
    args = parser.parse_args()

    # The console this is read on is a Windows one, whose default codepage cannot encode the
    # arrow below. Without this the script dies on its own output.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    by_name: dict[str, dict[str, pathlib.Path]] = defaultdict(dict)
    for label, package in MODULES.items():
        root = REPO / "modules" / package
        if not root.is_dir():
            # Loud and fatal. A missing directory used to be a warning, and a measurement that
            # reports nothing because it looked nowhere is worse than no measurement at all.
            print(f"{label}: no modules/{package}/ directory", file=sys.stderr)
            return 2
        for path in root.rglob("*.py"):
            if path.name == "__init__.py":
                continue
            by_name[str(path.relative_to(root))][label] = path

    rows = []
    copied_lines = 0
    for name, holders in by_name.items():
        if len(holders) < 2:
            continue
        for left, right in itertools.combinations(sorted(holders), 2):
            percentage, common = identity(holders[left], holders[right])
            if percentage >= args.threshold:
                rows.append((percentage, name, left, right))
            if percentage >= args.twin_at:
                # The second copy is the one that would not have to exist.
                copied_lines += common

    rows.sort(reverse=True)
    print(f"{'IDENT':>7}  {'FILE':<26}  PAIR")
    for percentage, name, left, right in rows:
        print(f"{percentage:6.1f}%  {name:<26}  {left} ↔ {right}")

    twins = sum(1 for row in rows if row[0] >= args.twin_at)
    print(
        f"\n{twins} pair(s) at or above {args.twin_at:g}%: "
        f"about {copied_lines} lines exist only as a copy of another module's."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
