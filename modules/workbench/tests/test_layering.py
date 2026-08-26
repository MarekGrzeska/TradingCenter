"""The rule that replaced "no module imports another module" inside this process: `agent`, `teams` and
`teams_tools` import none of the others, and `workbench/` is the only place that may import all three.

Read from the AST rather than the top of the file, so an import inside a function body counts too.
`importlib` slips past this, and that is accepted: it is not a mistake anybody makes by accident."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

MODULE_ROOT = Path(__file__).resolve().parent.parent

FORBIDDEN = {
    "agent": {"teams", "teams_tools", "workbench"},
    "teams": {"agent", "teams_tools", "workbench"},
    "teams_tools": {"agent", "teams", "workbench"},
}


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


def test_the_assembly_is_the_one_place_that_knows_all_three() -> None:
    """Stated as a positive so the rule cannot be satisfied by nothing importing anything:
    if `workbench` stopped reaching all three, something else would have had to."""
    imported: set[str] = set()
    for path in _sources("workbench"):
        imported |= _imported_top_level_packages(ast.parse(path.read_text(encoding="utf-8")))
    assert {"agent", "teams", "teams_tools"} <= imported
