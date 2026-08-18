"""The deploy workflows read as data, so their agreement with the shared one is testable.

Nothing checked that seven hand-copied workflows agreed, which is how the 16 August lesson
reached two of them and not the other five. One shared workflow removes most of that, and
what is left — a caller naming an input that does not exist, a path filter that never fires,
a value interpolated in a way that changes it — is what these tests hold.

One of them is written from a bug found while writing this change rather than from a
theory: `body_contains` is `"status"`, quotes included, and interpolated straight into a
quoted shell argument it collapses to `status`, which also matches a platform sign-in page.
The check would still have passed CI, still have gone green, and quietly stopped asserting
what it was added to assert.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

WORKFLOWS = Path(__file__).resolve().parents[2] / ".github" / "workflows"
SHARED = WORKFLOWS / "_deploy-app-service.yml"
SHARED_REF = "./.github/workflows/_deploy-app-service.yml"

# Not an App Service: a Static Web App, deployed by a different action, with no image and no
# container to probe. It is the one deploy workflow that is not a caller.
NOT_A_CALLER = {"deploy-terminal.yml"}


# `dict[Any, Any]`, not `dict[str, Any]`: `on:` parses as the boolean True under YAML 1.1,
# so the top-level keys are not all strings.
def load(path: Path) -> dict[Any, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def callers() -> list[Path]:
    """Deploy workflows that delegate to the shared one — all seven once group 4 lands."""
    found: list[Path] = []
    for path in sorted(WORKFLOWS.glob("deploy-*.yml")):
        if path.name in NOT_A_CALLER:
            continue
        jobs = load(path).get("jobs", {})
        if any(job.get("uses") == SHARED_REF for job in jobs.values()):
            found.append(path)
    return found


def shared_inputs() -> dict[str, Any]:
    # `on:` parses as the boolean True in YAML 1.1, which is why this is not `["on"]`.
    return load(SHARED)[True]["workflow_call"]["inputs"]


def probe_step() -> dict[str, Any]:
    steps = load(SHARED)["jobs"]["deploy"]["steps"]
    for step in steps:
        if "deploy_probe.py" in step.get("run", ""):
            return step
    raise AssertionError("the shared workflow has no step running deploy_probe.py")


def test_there_is_at_least_one_caller() -> None:
    assert callers(), "the shared workflow with no callers is dead weight"


@pytest.mark.parametrize("path", callers(), ids=lambda p: p.name)
class TestEveryCaller:
    def test_passes_only_inputs_the_shared_workflow_declares(self, path: Path) -> None:
        declared = set(shared_inputs())
        for name, job in load(path)["jobs"].items():
            if job.get("uses") != SHARED_REF:
                continue
            unknown = set(job.get("with", {})) - declared
            assert not unknown, f"{path.name}:{name} passes undeclared input(s) {unknown}"

    def test_names_its_module_and_its_app(self, path: Path) -> None:
        for job in load(path)["jobs"].values():
            if job.get("uses") != SHARED_REF:
                continue
            given = job.get("with", {})
            assert given.get("module"), "the module is the image suffix and the cache scope"
            assert str(given.get("app_name", "")).startswith("app-tradingcenter-")

    def test_watches_the_shared_workflow_and_the_probe(self, path: Path) -> None:
        """A caller blind to either would keep deploying an image built the old way."""
        paths = load(path)[True]["push"]["paths"]
        assert ".github/workflows/_deploy-app-service.yml" in paths
        assert "scripts/deploy_probe.py" in paths

    def test_watches_its_own_module_and_itself(self, path: Path) -> None:
        module = next(
            job["with"]["module"]
            for job in load(path)["jobs"].values()
            if job.get("uses") == SHARED_REF
        )
        paths = load(path)[True]["push"]["paths"]
        assert f"modules/{module}/**" in paths
        assert f".github/workflows/{path.name}" in paths

    def test_deploys_only_from_main(self, path: Path) -> None:
        """The pull_request federated credential cannot authenticate to Azure at all."""
        assert load(path)[True]["push"]["branches"] == ["main"]


class TestSharedWorkflow:
    def test_declares_the_production_environment(self) -> None:
        """`github-oidc.tf` puts `:environment:production` in the credential's subject."""
        assert load(SHARED)["jobs"]["deploy"]["environment"] == "production"

    def test_never_cancels_a_deploy_mid_flight(self) -> None:
        concurrency = load(SHARED)["jobs"]["deploy"]["concurrency"]
        assert concurrency["cancel-in-progress"] is False
        assert "${{ inputs.module }}" in concurrency["group"]

    def test_asks_for_the_permissions_the_deploy_needs(self) -> None:
        permissions = load(SHARED)["permissions"]
        assert permissions["id-token"] == "write"  # azure/login's OIDC exchange
        assert permissions["packages"] == "write"  # docker push to GHCR

    def test_tags_the_image_with_the_commit_and_never_latest(self) -> None:
        steps = load(SHARED)["jobs"]["deploy"]["steps"]
        build = next(s for s in steps if str(s.get("uses", "")).startswith("docker/build-push"))
        assert "${{ github.sha }}" in build["with"]["tags"]
        assert "latest" not in build["with"]["tags"]

    def test_the_probe_reads_its_values_from_env_not_from_interpolation(self) -> None:
        """The bug this file's docstring describes: `"status"` collapsing to `status`."""
        step = probe_step()
        assert "${{" not in step["run"], (
            "an interpolated value lands in the shell line unquoted — `body_contains` is "
            '`"status"` and would lose its quotes'
        )
        for variable in ("BODY_CONTAINS", "EXPECTED_IMAGE", "APP_NAME", "FAILURE_HINT"):
            assert f'"${variable}"' in step["run"], f"{variable} must arrive quoted"
            assert variable in step["env"]

    def test_the_probe_runs_from_the_scripts_project(self) -> None:
        """`uv run` outside `scripts/` resolves no lock, so httpx would be missing."""
        assert probe_step()["working-directory"] == "scripts"
