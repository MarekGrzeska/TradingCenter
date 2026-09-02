"""The duplication measurement is what condition 1 of the sharing rule rests on, and its module list
is hand-kept. That list named three deleted modules and none of the four newest for twelve days,
which is a measurement reading zero because it looked nowhere. These tests are the guard."""

from __future__ import annotations

import importlib.util
import pathlib
import subprocess
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "scripts" / "measure-duplication.py"


def measure():
    """Imported by path: the file has a hyphen in its name, so it is not an importable module."""
    spec = importlib.util.spec_from_file_location("measure_duplication", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def python_packages() -> set[str]:
    """Every Python package under `modules/`, read off git rather than the filesystem: a working
    copy keeps directories `git rm` already removed."""
    out = subprocess.run(
        ["git", "ls-files", "-z", "modules"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    packages = set()
    for path in out.split("\0"):
        parts = path.split("/")
        # modules/<module>/<package>/__init__.py, and nothing from a test tree.
        if len(parts) == 4 and parts[3] == "__init__.py" and parts[2] != "tests":
            packages.add(f"{parts[1]}/{parts[2]}")
    return packages


def test_every_python_package_is_measured() -> None:
    modules = measure().MODULES
    found = python_packages()
    assert found, "found no Python packages under modules/ to check the list against"

    missing = sorted(found - set(modules.values()))
    assert not missing, (
        f"measure-duplication.py does not measure {', '.join(missing)}. A package outside the "
        "list is one the sharing rule's own number cannot see."
    )


def test_the_list_names_nothing_that_is_gone() -> None:
    """The failure that made this test worth writing: the list survived four modules being deleted
    and reported a clean zero, because a missing directory was a warning on stderr."""
    modules = measure().MODULES
    stale = sorted(
        package for package in modules.values() if not (REPO_ROOT / "modules" / package).is_dir()
    )
    assert not stale, f"measure-duplication.py names {', '.join(stale)}, which no longer exists."


def test_the_script_runs_and_reports() -> None:
    """End to end, because the two lists above can both be right while the run itself is broken.
    It has been: the arrow in the output killed the script on a Windows console."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--threshold", "70"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "pair(s) at or above" in result.stdout
