"""The two rules that make this a platform rather than one strategy with ambitions: the pure layer imports
nothing of this module but the contract and reaches for no I/O or clock, and the runtime imports the
catalogue and never an entry in it.

Read from the AST rather than from the top of the file, so an import inside a function body counts too.
`importlib` slips past this, and that is accepted: it is not a mistake anybody makes by accident."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parent.parent / "strategy"

# What the pure layer is allowed to know about this module. `rule` and `periods` are contract, not
# runtime: the vocabulary a written rule is spelled in, and the archive's list of resolutions.
PURE_MAY_IMPORT = {"spec", "errors", "rule", "periods", "interpreter"}

# The pure files that do not live under `catalogue/`.
PURE_MODULES = ("rule.py", "interpreter.py")

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
RUNTIME_MODULES = (
    "archive.py",
    "store.py",
    "app.py",
    "gates.py",
    "resolver.py",
    "rule_validation.py",
)


def _sources(package: str) -> list[Path]:
    return sorted((PACKAGE_ROOT / package).rglob("*.py"))


def _entries() -> list[Path]:
    """The entry modules — the catalogue without its registry.

    `catalogue/__init__.py` imports every entry, and that is its whole job: it is the one
    file a new strategy changes. The rules below are about what an *entry* may know.
    """
    return [path for path in _sources("catalogue") if path.name != "__init__.py"]


def _pure() -> list[Path]:
    """Everything held to the entry's rule: the entries, plus the rule vocabulary and the
    interpreter that evaluates it."""
    return _entries() + [PACKAGE_ROOT / name for name in PURE_MODULES]


def _catalogue_module_names() -> set[str]:
    """The entries' own module names, allowed as imports of one another: the rule-as-data twin reads the
    fact keys the coded entry declares, and a second copy of those constants is how a twin stops being one."""
    return {path.stem for path in _entries()}


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


@pytest.mark.parametrize("path", _pure(), ids=lambda p: p.name)
def test_an_entry_knows_only_the_contract(path: Path) -> None:
    allowed = PURE_MAY_IMPORT | {"catalogue"} | _catalogue_module_names()
    reached = _own_modules_imported(_tree(path)) - allowed
    assert not reached, (
        f"{path.name} imports {', '.join(sorted(reached))} from this module. A catalogue "
        "entry may know the contract and nothing else — the moment it knows the runtime, "
        "the runtime cannot change without it."
    )


@pytest.mark.parametrize("path", _pure(), ids=lambda p: p.name)
def test_an_entry_does_no_io(path: Path) -> None:
    reached = _top_level_packages_imported(_tree(path)) & FORBIDDEN_PACKAGES
    assert not reached, f"{path.name} imports {', '.join(sorted(reached))}"


@pytest.mark.parametrize("path", _pure(), ids=lambda p: p.name)
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


# Every way this module could come to touch an account, written as words that would have to appear in a
# URL, a setting or a call. `order` and `position` cover being wired to the account by hand.
ACCOUNT_WORDS = (
    "trading_mcp",
    "trading-mcp",
    "TRADING_MCP",
    "capital_gateway",
    "capital-gateway",
    "CAPITAL_GATEWAY",
    "place_order",
    "close_position",
    "amend_stops",
)


def test_nothing_in_this_module_can_reach_an_account() -> None:
    """The platform decides and records; execution belongs to the teams. Asserted over the whole package
    rather than at one seam, because the claim is that there is no seam: no client, no setting, no call."""
    offences: list[str] = []
    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for word in ACCOUNT_WORDS:
            if word in text:
                offences.append(f"{path.name} mentions {word}")
    assert not offences, "\n".join(offences)


def _runtime_sources() -> list[Path]:
    paths = [path for package in RUNTIME_PACKAGES for path in _sources(package)]
    paths += [PACKAGE_ROOT / name for name in RUNTIME_MODULES]
    return sorted(path for path in paths if path.is_file())


@pytest.mark.parametrize("path", _runtime_sources(), ids=lambda p: p.name)
def test_the_runtime_never_names_a_strategy(path: Path) -> None:
    """The runtime knows the catalogue and never an entry in it — the whole claim of the change, in the
    only form a test can hold."""
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
