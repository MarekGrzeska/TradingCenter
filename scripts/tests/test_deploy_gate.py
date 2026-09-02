"""The gate's one decision, with the two fakes it needs: which heads are green, and what git says about them."""

from __future__ import annotations

from collections.abc import Sequence

from deploy_gate import Decision, decide, previous_green

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
