"""Does this deploy have anything to deploy? A workflow started by `workflow_run` has no path filter, so the
question moves here: did anything this image bakes in change since the last commit that could have reached
production — the head of the previous green `checks` run on the branch. Not `HEAD^`: two merges minutes apart
cancel the first one's checks, and a diff against `HEAD^` would drop that merge's modules on the floor."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass

# The events under which the gate has an opinion. Anything else — a pull request preview, a dispatch from the
# operator — deploys without asking, because there the trigger itself is the decision.
GATED_EVENT = "workflow_run"


@dataclass(frozen=True)
class Decision:
    deploy: bool
    base: str | None
    reason: str


IsAncestor = Callable[[str, str], bool]
Changed = Callable[[str, str, Sequence[str]], bool]


def _same_commit(one: str, other: str) -> bool:
    """A full sha and its abbreviation name one commit; the operator's hand types the short one."""
    return one.startswith(other) or other.startswith(one)


def previous_green(sha: str, green_heads: Sequence[str], is_ancestor: IsAncestor) -> str | None:
    """The newest green head that is not this commit and lies behind it. This commit's own run is in the
    list — it is the one that started us — and a head off a rewritten history is not a base for anything."""
    for head in green_heads:
        if not _same_commit(head, sha) and is_ancestor(head, sha):
            return head
    return None


def decide(
    *,
    event: str,
    sha: str,
    paths: Sequence[str],
    green_heads: Sequence[str],
    is_ancestor: IsAncestor,
    changed: Changed,
) -> Decision:
    if event != GATED_EVENT:
        return Decision(True, None, f"{event} deploys without asking what changed")
    base = previous_green(sha, green_heads, is_ancestor) or f"{sha}^"
    if changed(base, sha, paths):
        return Decision(True, base, f"something under {list(paths)} changed since {base}")
    return Decision(False, base, f"nothing under {list(paths)} changed since {base}")


def _green_heads(workflow: str, branch: str, limit: int) -> list[str]:
    out = subprocess.run(
        [
            "gh",
            "run",
            "list",
            "--workflow",
            workflow,
            "--branch",
            branch,
            "--status",
            "success",
            "--json",
            "headSha",
            "--limit",
            str(limit),
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return [run["headSha"] for run in json.loads(out)]


def repository_root() -> str:
    """Where a pathspec is relative to. The gate runs from `scripts/`, where `uv run` finds its lock, and git
    resolves `modules/workbench` against the working directory: on 2 September 2026 every deploy of f5a78b2
    reported "nothing changed" and skipped, because it was looking for `scripts/modules/workbench`."""
    return subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], check=True, capture_output=True, text=True
    ).stdout.strip()


def _is_ancestor(base: str, sha: str) -> bool:
    command = ["git", "merge-base", "--is-ancestor", base, sha]
    return subprocess.run(command, check=False, cwd=repository_root()).returncode == 0


def _changed(base: str, sha: str, paths: Sequence[str]) -> bool:
    # `--quiet` exits 1 when there is a difference — that is the answer, not a failure.
    command = ["git", "diff", "--quiet", base, sha, "--", *paths]
    return subprocess.run(command, check=False, cwd=repository_root()).returncode == 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event", required=True, help="github.event_name")
    parser.add_argument("--sha", required=True, help="the commit the checks ran on")
    parser.add_argument(
        "--paths", required=True, help="git pathspecs, one per line — what the image bakes in"
    )
    parser.add_argument("--workflow", default="checks.yml")
    parser.add_argument("--branch", default="main")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args(argv)

    paths = [line.strip() for line in args.paths.splitlines() if line.strip()]
    green = (
        _green_heads(args.workflow, args.branch, args.limit) if args.event == GATED_EVENT else []
    )
    decision = decide(
        event=args.event,
        sha=args.sha,
        paths=paths,
        green_heads=green,
        is_ancestor=_is_ancestor,
        changed=_changed,
    )
    print(decision.reason)

    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(f"deploy={'true' if decision.deploy else 'false'}\n")
            handle.write(f"sha={args.sha}\n")
            handle.write(f"base={decision.base or ''}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
