#!/usr/bin/env python3
"""How much of the Python here is a hand-maintained copy of other Python here — the number condition 1
of `docs/architecture.md`'s sharing rule rests on, so somebody who was not there can take it again.

    uv run --no-project python scripts/measure-duplication.py --threshold 40

Per pair of modules holding a file of the same name, the fraction of lines in common by
`difflib.SequenceMatcher` with `autojunk` off; comments count, because prose kept in step is a copy too.
Taken 18 August 2026, before `tc-runtime`: 959 lines lived as copies, in seven pairs at or above 70%.
"""

from __future__ import annotations

import argparse
import difflib
import itertools
import pathlib
import sys
from collections import defaultdict

REPO = pathlib.Path(__file__).resolve().parent.parent

# module directory -> its import package. Kept explicit rather than globbed: a new module
# is a line here, and a module that is not Python has no business being guessed at.
MODULES = {
    "agent": "agent",
    "teams": "teams",
    "market-data": "market_data",
    "capital-gateway": "capital_gateway",
    "teams-mcp": "teams_mcp",
    "trading-mcp": "trading_mcp",
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

    by_name: dict[str, dict[str, pathlib.Path]] = defaultdict(dict)
    for module, package in MODULES.items():
        root = REPO / "modules" / module / package
        if not root.is_dir():
            print(f"skipping {module}: no {package}/ directory", file=sys.stderr)
            continue
        for path in root.rglob("*.py"):
            if path.name == "__init__.py":
                continue
            by_name[str(path.relative_to(root))][module] = path

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
