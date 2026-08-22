"""The two rules that make this a platform rather than one strategy with ambitions.

    strategy/catalogue/**   MUST import nothing of this module but `spec` and `errors`,
                            and MUST NOT reach for I/O or a clock
    the runtime             MUST NOT import an individual catalogue entry — only the
                            catalogue itself

The second is "adding a strategy changes no file of the runtime" in its enforceable form.
The first is what makes `evaluate` a pure function, which everything downstream stands on:
the unit tests that hand it facts by hand, the replay of a recorded decision, and the
backtest calling the very same function the loop calls.

Read from the AST rather than from the top of the file, so an import tucked inside a
function body counts too. `importlib` would slip past this, and that is accepted:
`importlib` is not a mistake anybody makes by accident, and this rule is here for the
mistakes that are. The shape is `workbench/tests/test_layering.py`'s, which is the same
rule one level up.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parent.parent / "strategy"

# What a catalogue entry is allowed to know about this module. Anything else — the archive
# client, the store, the loop, the surfaces, even the settings — is the runtime, and an
# entry that reached for it would stop being a function of its arguments.
CATALOGUE_MAY_IMPORT = {"spec", "errors"}

# Reaching outside the process at all. A pure function has no business with any of these,
# and each of them is how a strategy would stop being replayable without looking wrong.
FORBIDDEN_PACKAGES = {"httpx", "asyncpg", "fastapi", "starlette", "mcp", "time", "random"}

# The clock, by the names it actually goes by. A strategy reads `Facts.as_of`, which is the
# bar's own closing time — a decision that consulted the wall clock would replay to a
# different answer tomorrow.
CLOCK_ATTRIBUTES = {"now", "utcnow", "today", "monotonic", "time"}

# Everything that is the runtime. These may import `catalogue`; none of them may import a
# module *inside* it.
RUNTIME_PACKAGES = ("runner", "routers", "tools", "backtest")
RUNTIME_MODULES = ("archive.py", "store.py", "app.py", "gates.py")


def _sources(package: str) -> list[Path]:
    return sorted((PACKAGE_ROOT / package).rglob("*.py"))


def _entries() -> list[Path]:
    """The entry modules — the catalogue without its registry.

    `catalogue/__init__.py` imports every entry, and that is its whole job: it is the one
    file a new strategy changes. The rules below are about what an *entry* may know.
    """
    return [path for path in _sources("catalogue") if path.name != "__init__.py"]


def _tree(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"))


def _own_modules_imported(tree: ast.AST) -> set[str]:
    """Which modules of this package a file imports, however it spells the import.

    `from ..archive import X` and `from strategy.archive import X` are the same reach and
    are counted the same; a relative import's first component is what this returns.
    """
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level > 0 and node.module:
                names.add(node.module.split(".")[0])
            elif node.level > 0 and node.module is None:
                # `from .. import archive` — the names are the modules.
                names.update(alias.name.split(".")[0] for alias in node.names)
            elif node.module and node.module.split(".")[0] == "strategy":
                parts = node.module.split(".")
                if len(parts) > 1:
                    names.add(parts[1])
        elif isinstance(node, ast.Import):
            for alias in node.names:
                parts = alias.name.split(".")
                if parts[0] == "strategy" and len(parts) > 1:
                    names.add(parts[1])
    return names


def _top_level_packages_imported(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


@pytest.mark.parametrize("path", _entries(), ids=lambda p: p.name)
def test_an_entry_knows_only_the_contract(path: Path) -> None:
    reached = _own_modules_imported(_tree(path)) - CATALOGUE_MAY_IMPORT - {"catalogue"}
    assert not reached, (
        f"{path.name} imports {', '.join(sorted(reached))} from this module. A catalogue "
        "entry may know the contract and nothing else — the moment it knows the runtime, "
        "the runtime cannot change without it."
    )


@pytest.mark.parametrize("path", _entries(), ids=lambda p: p.name)
def test_an_entry_does_no_io(path: Path) -> None:
    reached = _top_level_packages_imported(_tree(path)) & FORBIDDEN_PACKAGES
    assert not reached, f"{path.name} imports {', '.join(sorted(reached))}"


@pytest.mark.parametrize("path", _entries(), ids=lambda p: p.name)
def test_an_entry_does_not_read_a_clock(path: Path) -> None:
    """A decision belongs to a bar. One that consulted the wall clock would replay to a
    different answer tomorrow, and the replay is what makes a recorded decision evidence."""
    offences = [
        node.attr
        for node in ast.walk(_tree(path))
        if isinstance(node, ast.Attribute) and node.attr in CLOCK_ATTRIBUTES
    ]
    assert not offences, (
        f"{path.name} reaches for {', '.join(sorted(set(offences)))}. A strategy reads "
        "`Facts.as_of` — the closing time of the bar it is deciding on."
    )


def _runtime_sources() -> list[Path]:
    paths = [path for package in RUNTIME_PACKAGES for path in _sources(package)]
    paths += [PACKAGE_ROOT / name for name in RUNTIME_MODULES]
    return sorted(path for path in paths if path.is_file())


@pytest.mark.parametrize("path", _runtime_sources(), ids=lambda p: p.name)
def test_the_runtime_never_names_a_strategy(path: Path) -> None:
    """The runtime knows the catalogue and never an entry in it.

    This is the whole claim of the change, in the only form a test can hold: if no file of
    the runtime can name `catalogue.baseline`, then adding `catalogue.something_else`
    cannot require one of them to change.
    """
    offences: list[str] = []
    for node in ast.walk(_tree(path)):
        if isinstance(node, ast.ImportFrom) and node.module:
            parts = node.module.split(".")
            # `from ..catalogue.baseline import x` (relative) or the absolute spelling.
            if "catalogue" in parts and parts[-1] != "catalogue":
                offences.append(node.module)
            # `from ..catalogue import baseline`
            if parts[-1] == "catalogue":
                offences += [
                    f"{node.module}.{alias.name}"
                    for alias in node.names
                    # The registry's own public names; anything else is an entry module.
                    if alias.name
                    not in {"get", "all_entries", "check_facts_are_announced", "CATALOGUE"}
                ]
    assert not offences, (
        f"{path.name} imports {', '.join(offences)}. The runtime may know the catalogue; "
        "naming an entry in it is what makes the next strategy a change to this file."
    )
