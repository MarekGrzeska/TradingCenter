"""The `changes` filter in `checks.yml`, run rather than read: every other job depends on it, so a mistake is a
repository where no pull request runs anything. Iteration 1's unassigned variable was found by running it."""

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


def _bash_has_associative_arrays() -> bool:
    """The step's own shell needs `declare -A`, which arrived in bash 4. macOS ships 3.2.57, so gating on
    "is there a bash" passed here and failed every test in the file. Ask the shell what it can do."""
    if BASH is None:
        return False
    probe = subprocess.run(
        [BASH, "-c", "declare -A probe"], capture_output=True, check=False
    )
    return probe.returncode == 0


pytestmark = pytest.mark.skipif(
    not _bash_has_associative_arrays(),
    reason="needs bash 4+ for `declare -A`; macOS ships 3.2 (CI runs Ubuntu)",
)


def filter_script() -> str:
    """The step's `run:` block from the line after the `git diff`: everything before it is the base-commit
    dance, which needs a GitHub event, and everything after needs only a list of file names."""
    workflow = yaml.safe_load(CHECKS.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["changes"]["steps"]
    step = next(s for s in steps if s.get("id") == "filter")
    lines = step["run"].splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("changed=")) + 1
    return "\n".join(lines[start:])


def run_step(changed: list[str], cwd: Path) -> tuple[subprocess.CompletedProcess[str], str]:
    """The step's own shell on a synthetic diff. `cwd` matters: the step reads `packages/` to decide the
    matrix, so a run that cannot see that directory answers a question CI never asks."""
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
    """The job decisions alone. The step writes one more output than there are jobs — `package-list`, the
    matrix — and it is not a decision."""
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
    decisions = decide(["README.md", "docs/architecture.md"])
    assert not any(decisions.values()), decisions


class TestOneFileAtATime:
    def test_infra_runs_the_infra_job_and_nothing_else(self) -> None:
        decisions = decide(["infra/main.tf"])
        assert decisions["infra"]
        assert not decisions["workbench"]
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
        decisions = decide(["modules/workbench/agent/turn.py"])
        assert decisions["workbench"]
        assert not decisions["market-data"]

    def test_market_datas_contract_reaches_the_terminal(self) -> None:
        """The terminal keeps generated types built from that schema, and `contract:check` only runs if its
        job does. The second copy — market-mcp's snapshot — is gone with the module that held it."""
        decisions = decide(["modules/market-data/market_data/contract.py"])
        assert decisions["market-data"]
        assert decisions["terminal"]

    def test_the_gateway_reaches_trading_mcp(self) -> None:
        """trading-mcp keeps a snapshot of the gateway's whole OpenAPI document."""
        decisions = decide(["modules/capital-gateway/capital_gateway/app.py"])
        assert decisions["capital-gateway"]
        assert decisions["trading-mcp"]

    def test_the_teams_surface_reaches_the_terminal(self) -> None:
        """`weekdays-on-the-shorter-rhythms` measured why the filter is the whole module: it touched only
        `recurrence.py`, whose docstring *is* a description in the schema."""
        decisions = decide(["modules/workbench/teams/recurrence.py"])
        assert decisions["workbench"]
        assert decisions["terminal"]

    def test_polymarket_datas_contract_reaches_the_terminal(self) -> None:
        """Its `contract.py` and `openapi.py` rather than the whole module: the second marks every response
        field required, so it moves the generated types with no edit to the first."""
        decisions = decide(["modules/polymarket-data/polymarket_data/contract.py"])
        assert decisions["polymarket-data"]
        assert decisions["terminal"]

        shaping = decide(["modules/polymarket-data/polymarket_data/openapi.py"])
        assert shaping["terminal"]

    def test_the_rest_of_polymarket_data_leaves_the_terminal_alone(self) -> None:
        """The other half of the pairing: a module's own work is not the terminal's."""
        decisions = decide(["modules/polymarket-data/polymarket_data/ingest.py"])
        assert decisions["polymarket-data"]
        assert not decisions["terminal"]

    def test_a_package_runs_every_module_that_takes_it(self) -> None:
        """The whole price of sharing source, paid in CI rather than in production."""
        decisions = decide(["packages/tc-runtime/tc_runtime/db.py"])
        assert decisions["packages"]
        assert decisions["workbench"]
        assert decisions["market-data"]

    def test_tc_openai_reaches_only_its_consumer(self) -> None:
        """Two consumers became one when they became one module; the property this holds is the other half,
        that a package's edit must not run a module which does not take it."""
        decisions = decide(["packages/tc-openai/tc_openai/provider.py"])
        assert decisions["workbench"]
        assert not decisions["market-data"]
        assert not decisions["trading-mcp"]

    def test_tc_mcp_kit_reaches_everything_that_speaks_mcp(self) -> None:
        """The archive, trading-mcp and the workbench — the last two hold a database, which is why the old
        reason for this package existing apart from `tc-runtime` had to be rewritten twice."""
        decisions = decide(["packages/tc-mcp-kit/tc_mcp_kit/network_identity.py"])
        assert decisions["market-data"]
        assert decisions["trading-mcp"]
        assert decisions["workbench"]
        assert not decisions["capital-gateway"]


class TestTheMatrixTheJobRuns:
    """`package-list` is the diff intersected with `packages/`. Neither half alone is right: the directory
    runs all three for a one-package edit, the diff hands the matrix a package the pull request deletes."""

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
        """The guard's own failure mode, and why the loops read line by line: a directory name with a space
        survives to be refused instead of being split into two names that both look fine."""
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
