"""The gate's one decision, with the two fakes it needs: which heads are green, and what git says about them."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest

from deploy_gate import Decision, _changed, decide, previous_green

# A main branch as git sees it: each commit's ancestors are the ones before it.
HISTORY = ["c1", "c2", "c3", "c4"]


def is_ancestor(base: str, sha: str) -> bool:
    return base in HISTORY and sha in HISTORY and HISTORY.index(base) < HISTORY.index(sha)


def changed_under(*touched: str):
    """A diff fake keyed on pathspec prefixes, so a test names what a merge touched rather than a whole tree."""

    def changed(base: str, sha: str, paths: Sequence[str]) -> bool:
        return any(t.startswith(p) for t in touched for p in paths)

    return changed


def gate(
    *, event: str = "workflow_run", sha: str = "c4", green: Sequence[str] = ("c4", "c2"), touched=()
) -> Decision:
    return decide(
        event=event,
        sha=sha,
        paths=["modules/workbench", "packages/tc-runtime"],
        green_heads=green,
        is_ancestor=is_ancestor,
        changed=changed_under(*touched),
    )


def test_the_base_is_the_previous_green_head_not_the_parent() -> None:
    """The reason this file exists: c3's checks were cancelled by c4's push, so c3's modules would
    be lost against `HEAD^`. Against the last green head they are inside the range."""
    assert previous_green("c4", ["c4", "c2", "c1"], is_ancestor) == "c2"


def test_this_commits_own_green_run_is_not_its_base() -> None:
    assert previous_green("c4", ["c4"], is_ancestor) is None


def test_a_green_head_off_a_rewritten_history_is_skipped() -> None:
    assert previous_green("c4", ["c4", "elsewhere", "c1"], is_ancestor) == "c1"


def test_no_green_run_falls_back_to_the_parent() -> None:
    decision = gate(green=["c4"], touched=("modules/workbench/app.py",))
    assert decision.base == "c4^"
    assert decision.deploy is True


def test_a_change_under_a_watched_path_deploys() -> None:
    decision = gate(touched=("packages/tc-runtime/db.py",))
    assert decision.deploy is True
    assert decision.base == "c2"


def test_a_change_elsewhere_does_not() -> None:
    decision = gate(touched=("modules/strategy/app.py", "README.md"))
    assert decision.deploy is False
    assert decision.base == "c2"


def test_a_dispatch_deploys_without_asking() -> None:
    """The operator's door: `workflow_dispatch` is the decision, so the gate has no opinion."""
    decision = gate(event="workflow_dispatch", touched=())
    assert decision.deploy is True
    assert decision.base is None


def test_a_pull_request_preview_deploys_without_asking() -> None:
    assert gate(event="pull_request", touched=()).deploy is True


def test_an_abbreviated_sha_names_the_same_commit_as_its_full_form() -> None:
    assert previous_green("c4", ["c4full", "c2"], lambda b, s: True) == "c2"


def _git(repo: Path, *args: str) -> str:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@x",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@x",
    }
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True, env=env
    ).stdout.strip()


def test_the_diff_is_taken_from_the_repository_root_not_the_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Written from the first live run, 2 September 2026: the gate runs from `scripts/`, git resolved
    `modules/workbench` against it, and every deploy of f5a78b2 skipped on "nothing changed"."""
    repo = tmp_path / "repo"
    (repo / "modules" / "x").mkdir(parents=True)
    (repo / "scripts").mkdir()
    _git(repo, "init", "-q", "-b", "main")
    (repo / "modules" / "x" / "a.txt").write_text("one", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "one")
    first = _git(repo, "rev-parse", "HEAD")
    (repo / "modules" / "x" / "a.txt").write_text("two", encoding="utf-8")
    _git(repo, "commit", "-q", "-am", "two")
    second = _git(repo, "rev-parse", "HEAD")

    monkeypatch.chdir(repo / "scripts")

    assert _changed(first, second, ["modules/x"]) is True
    assert _changed(first, second, ["modules/y"]) is False
