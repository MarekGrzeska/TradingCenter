"""The rule that replaced "no module imports another module" inside this process: the packages listed below import
none of the others, and `workbench/` alone may import all of them. Read from the AST, so an import in a function counts."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

MODULE_ROOT = Path(__file__).resolve().parent.parent

# The packages that share this process, and the one that assembles them. A package folded in later is one entry
# here, not a new row of forbidden pairs: every package is forbidden every other package and the assembly.
PACKAGES = ("agent", "teams", "teams_tools", "polymarket_data", "social_data", "strategy")
ASSEMBLY = "workbench"
FORBIDDEN = {package: (set(PACKAGES) - {package}) | {ASSEMBLY} for package in PACKAGES}


def _imported_top_level_packages(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


def _sources(package: str) -> list[Path]:
    return sorted((MODULE_ROOT / package).rglob("*.py"))


@pytest.mark.parametrize("package", sorted(FORBIDDEN))
def test_a_package_does_not_reach_into_its_neighbours(package: str) -> None:
    offences = []
    for path in _sources(package):
        imported = _imported_top_level_packages(ast.parse(path.read_text(encoding="utf-8")))
        for name in sorted(imported & FORBIDDEN[package]):
            offences.append(f"{path.relative_to(MODULE_ROOT)} imports {name}")
    assert not offences, "\n".join(offences)


def test_the_assembly_is_the_one_place_that_knows_every_package() -> None:
    """Stated as a positive so the rule cannot be satisfied by nothing importing anything:
    if `workbench` stopped reaching all of them, something else would have had to."""
    imported: set[str] = set()
    for path in _sources(ASSEMBLY):
        imported |= _imported_top_level_packages(ast.parse(path.read_text(encoding="utf-8")))
    assert set(PACKAGES) <= imported
