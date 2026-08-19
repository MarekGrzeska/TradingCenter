"""The `changes` filter in `checks.yml`, run rather than read.

Every other job in that workflow depends on this one step, so a mistake in it is not one
red job — it is a repository where no pull request runs any test. Iteration 1 found exactly
that: a pattern referring to a variable one line before it was assigned, which under
`set -u` would have brought the whole `changes` job down. It was found by *running* the step
on a synthetic diff, not by reading it, and this is that run kept.

The real shell is executed: only the GitHub context and the `git diff` are replaced, so
`matches`, the pattern table and the loop are the ones that will run in CI.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
CHECKS = ROOT / ".github" / "workflows" / "checks.yml"
BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(BASH is None, reason="needs bash to run the step's own shell")


def filter_script() -> str:
    """The step's `run:` block, from the line after the `git diff` onwards.

    Everything before it is the base-commit dance, which needs a GitHub event. Everything
    after is the decision, which needs only a list of file names.
    """
    workflow = yaml.safe_load(CHECKS.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["changes"]["steps"]
    step = next(s for s in steps if s.get("id") == "filter")
    lines = step["run"].splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("changed=")) + 1
    return "\n".join(lines[start:])


def run_step(changed: list[str], cwd: Path) -> tuple[subprocess.CompletedProcess[str], str]:
    """The step's own shell on a synthetic diff, and whatever it wrote to `GITHUB_OUTPUT`.

    `cwd` matters: the step reads `packages/` to decide which packages the matrix runs, so
    a run that cannot see that directory answers a question CI never asks. Only
    `GITHUB_OUTPUT` and the diff are replaced.
    """
    assert BASH is not None
    with tempfile.TemporaryDirectory() as directory:
        output = Path(directory) / "github_output"
        output.touch()
        script = "\n".join(
            [
                "set -euo pipefail",
                f'changed="{chr(10).join(changed)}"',
                filter_script(),
            ]
        )
        done = subprocess.run(
            [BASH, "-c", script],
            capture_output=True,
            text=True,
            check=False,
            cwd=cwd,
            env={"GITHUB_OUTPUT": str(output), "PATH": "/usr/bin:/bin"},
        )
        return done, output.read_text(encoding="utf-8")


def outputs(changed: list[str]) -> dict[str, str]:
    """Every `name=value` the step writes, verbatim, run against the real repository."""
    done, written_text = run_step(changed, ROOT)
    assert done.returncode == 0, f"the step itself failed:\n{done.stderr}"
    written: dict[str, str] = {}
    for line in written_text.splitlines():
        if "=" in line:
            name, _, value = line.partition("=")
            written[name] = value
    return written


def decide(changed: list[str]) -> dict[str, bool]:
    """The job decisions alone.

    The step writes one more output than there are jobs — `package-list`, the matrix — and
    it is not a decision. Reading only `true`/`false` keeps the two tests below, which pair
    every decision with a job that reads it, asking about the thing they were written for.
    """
    return {
        name: value == "true"
        for name, value in outputs(changed).items()
        if value in ("true", "false")
    }


def matrix(changed: list[str]) -> list[str]:
    return json.loads(outputs(changed)["package-list"])


def test_the_step_runs_at_all_under_set_u() -> None:
    """The failure iteration 1 caught: `set -u` bringing down the job everything needs."""
    assert decide(["README.md"])


def test_a_documentation_change_runs_nothing() -> None:
    decisions = decide(["README.md", "docs/plan-refactoru.html"])
    assert not any(decisions.values()), decisions


class TestOneFileAtATime:
    def test_infra_runs_the_infra_job_and_nothing_else(self) -> None:
        decisions = decide(["infra/main.tf"])
        assert decisions["infra"]
        assert not decisions["agent"]
        assert not decisions["terminal"]

    def test_bootstrap_counts_as_infra(self) -> None:
        """`infra/bootstrap/` is a separate root, and it was outside every check until now."""
        assert decide(["infra/bootstrap/main.tf"])["infra"]

    def test_the_dev_runner_runs_the_scripts_job(self) -> None:
        decisions = decide(["scripts/dev.py"])
        assert decisions["scripts"]
        assert not decisions["infra"]

    def test_the_archive_script_runs_openspec_as_well_as_scripts(self) -> None:
        """It is the shape the archive check enforces, so it is in both lists on purpose."""
        decisions = decide(["scripts/trim-openspec-archive.sh"])
        assert decisions["openspec"]
        assert decisions["scripts"]

    def test_a_module_runs_its_own_job(self) -> None:
        decisions = decide(["modules/agent/agent/loop.py"])
        assert decisions["agent"]
        assert not decisions["teams"]

    def test_market_datas_contract_reaches_the_terminal_and_market_mcp(self) -> None:
        """Both keep a copy of that schema; both checks only run if their job does."""
        decisions = decide(["modules/market-data/market_data/contract.py"])
        assert decisions["market-data"]
        assert decisions["terminal"]
        assert decisions["market-mcp"]

    def test_the_gateway_reaches_trading_mcp(self) -> None:
        """trading-mcp keeps a snapshot of the gateway's whole OpenAPI document."""
        decisions = decide(["modules/capital-gateway/capital_gateway/app.py"])
        assert decisions["capital-gateway"]
        assert decisions["trading-mcp"]

    def test_teams_reaches_teams_mcp_and_the_terminal(self) -> None:
        decisions = decide(["modules/teams/teams/recurrence.py"])
        assert decisions["teams"]
        assert decisions["teams-mcp"]
        assert decisions["terminal"]

    def test_a_package_runs_every_module_that_takes_it(self) -> None:
        """The whole price of sharing source, paid in CI rather than in production."""
        decisions = decide(["packages/tc-runtime/tc_runtime/db.py"])
        assert decisions["packages"]
        assert decisions["agent"]
        assert decisions["teams"]
        assert decisions["market-data"]

    def test_tc_openai_reaches_only_its_two_consumers(self) -> None:
        decisions = decide(["packages/tc-openai/tc_openai/provider.py"])
        assert decisions["agent"]
        assert decisions["teams"]
        assert not decisions["market-data"]

    def test_tc_mcp_kit_reaches_the_three_mcp_modules_and_no_others(self) -> None:
        decisions = decide(["packages/tc-mcp-kit/tc_mcp_kit/network_identity.py"])
        assert decisions["market-mcp"]
        assert decisions["trading-mcp"]
        assert decisions["teams-mcp"]
        assert not decisions["agent"]


class TestTheMatrixTheJobRuns:
    """`package-list`, which is the diff intersected with `packages/`.

    Neither half alone is right: the directory alone runs all three packages for a
    one-package edit, and the diff alone hands the matrix a package the pull request
    deletes, whose `working-directory` no longer exists.
    """

    def test_one_package_edit_runs_that_package_alone(self) -> None:
        assert matrix(["packages/tc-openai/tc_openai/provider.py"]) == ["tc-openai"]

    def test_two_packages_run_both(self) -> None:
        assert sorted(
            matrix(
                [
                    "packages/tc-openai/tc_openai/provider.py",
                    "packages/tc-runtime/tc_runtime/db.py",
                ]
            )
        ) == ["tc-openai", "tc-runtime"]

    def test_a_package_the_diff_deletes_is_not_in_the_matrix(self) -> None:
        """The reason this is an intersection rather than the diff: no directory to run in."""
        assert "tc-gone" not in matrix(["packages/tc-gone/tc_gone/thing.py"])

    def test_a_new_package_cannot_merge_untested(self) -> None:
        """What the directory listing was there for, and it survives the narrowing: a
        package added by a pull request is in that pull request's diff by definition."""
        added = min(p.name for p in (ROOT / "packages").iterdir() if p.is_dir())
        assert matrix([f"packages/{added}/pyproject.toml"]) == [added]

    def test_the_workflow_itself_runs_every_package(self) -> None:
        """An empty intersection means `packages` fired on checks.yml rather than on a
        package, and a change to how the checks run has to be exercised by running them."""
        on_disk = sorted(p.name for p in (ROOT / "packages").iterdir() if p.is_dir())
        assert sorted(matrix([".github/workflows/checks.yml"])) == on_disk

    def test_a_name_that_would_break_the_matrix_stops_the_step(self, tmp_path: Path) -> None:
        """The guard's own failure mode, which is why the loops read line by line: a
        directory name with a space survives to be refused instead of being split into
        two names that both look fine."""
        (tmp_path / "packages" / "tc-fine").mkdir(parents=True)
        (tmp_path / "packages" / "tc broken").mkdir()
        done, _ = run_step([".github/workflows/checks.yml"], tmp_path)
        assert done.returncode != 0
        assert "not matrix-safe" in done.stderr, done.stderr

    def test_the_guard_passes_the_names_this_repository_has(self, tmp_path: Path) -> None:
        """The other direction, so the test above is not passing on a step that refuses
        everything: the same tree without the bad name is accepted."""
        (tmp_path / "packages" / "tc-fine").mkdir(parents=True)
        (tmp_path / "packages" / "tc_also.fine").mkdir()
        done, _ = run_step([".github/workflows/checks.yml"], tmp_path)
        assert done.returncode == 0, done.stderr


def test_touching_the_workflow_runs_everything() -> None:
    """A change to how the checks run has to be exercised by running them."""
    decisions = decide([".github/workflows/checks.yml"])
    assert all(decisions.values()), {k: v for k, v in decisions.items() if not v}


def test_every_conditional_job_has_a_pattern_deciding_it() -> None:
    """A job whose name no pattern produces never runs, and nothing says so."""
    workflow = yaml.safe_load(CHECKS.read_text(encoding="utf-8"))
    gated = {
        name
        for name, job in workflow["jobs"].items()
        if "needs.changes.outputs." in str(job.get("if", ""))
    }
    decided = set(decide([".github/workflows/checks.yml"]))
    assert gated <= decided, f"no pattern decides {gated - decided}"


def test_every_pattern_gates_a_job_that_exists() -> None:
    """And the other direction: a pattern nobody reads is a decision with no consequence."""
    workflow = yaml.safe_load(CHECKS.read_text(encoding="utf-8"))
    decided = set(decide([".github/workflows/checks.yml"]))
    read_by_someone = {
        name
        for name in decided
        for job in workflow["jobs"].values()
        if f"needs.changes.outputs.{name}" in str(job.get("if", ""))
    }
    assert decided == read_by_someone, f"nothing reads {decided - read_by_someone}"
