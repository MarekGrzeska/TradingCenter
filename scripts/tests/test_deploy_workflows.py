"""The deploy workflows read as data, so their agreement with the shared one is testable — seven hand-copied
ones is how the 16 August lesson reached two and not the other five. One of these is written from a bug found
while writing it: `body_contains` interpolated into a quoted shell argument lost its quotes and matched a
sign-in page, which would have gone green while asserting nothing."""

from __future__ import annotations

import re
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


def probe_step() -> dict[str, Any]:
    steps = load(SHARED)["jobs"]["deploy"]["steps"]
    for step in steps:
        if "deploy_probe.py" in step.get("run", ""):
            return step
    raise AssertionError("the shared workflow has no step running deploy_probe.py")


def test_there_is_at_least_one_caller() -> None:
    assert callers(), "the shared workflow with no callers is dead weight"


def test_every_caller_declares_the_permissions_itself() -> None:
    """On the caller, and nowhere else will do: a reusable workflow can only *narrow* the caller's token, and
    `id-token` is never granted by default. Asserting it on `_deploy-app-service.yml` is what missed this."""
    for path in callers():
        permissions = load(path).get("permissions") or {}
        assert permissions.get("id-token") == "write", path.name  # azure/login's OIDC
        assert permissions.get("packages") == "write", path.name  # docker push to GHCR


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


def test_every_app_service_module_deploys_through_the_shared_workflow() -> None:
    """Read off `modules/`, because a typed list beside a directory reports green having tested something else.
    A module is a directory with a `Dockerfile`: an archived one leaves its name on disk long after git stops."""
    repo = Path(__file__).resolve().parents[2]
    app_service_modules = {
        path.name
        for path in (repo / "modules").iterdir()
        if path.is_dir() and (path / "Dockerfile").is_file()
    }

    deploying = {
        job["with"]["module"]
        for path in callers()
        for job in load(path)["jobs"].values()
        if job.get("uses") == SHARED_REF
    }

    assert deploying == app_service_modules


# Written from a failure on 19 August 2026: `market-data` took `tc-mcp-kit` and its Dockerfile still copied
# only `tc-runtime`. No module job builds an image, so the first thing to notice was `deploy-market-data`
# failing on `main` at `uv sync --frozen`. These two are the check that runs before that.

MODULES = Path(__file__).resolve().parents[2] / "modules"

WORKFLOW_NAMES = {"capital-gateway": "deploy-gateway.yml"}

PATH_DEPENDENCY = re.compile(r'^(tc-[a-z-]+)\s*=\s*\{\s*path\s*=\s*"\.\./\.\./packages/', re.MULTILINE)
DOCKERFILE_COPY = re.compile(r"^COPY packages/(tc-[a-z-]+) ", re.MULTILINE)


def modules_with_a_dockerfile() -> list[Path]:
    return sorted(p for p in MODULES.iterdir() if (p / "Dockerfile").is_file())


@pytest.mark.parametrize(
    "module", modules_with_a_dockerfile(), ids=lambda p: p.name
)
def test_the_image_copies_exactly_the_packages_the_module_takes(module: Path) -> None:
    """A package in `pyproject.toml` and not in the Dockerfile is a build that fails on `main`; one the other
    way round is a layer invalidated by source this image never installs."""
    pyproject = (module / "pyproject.toml").read_text(encoding="utf-8")
    dockerfile = (module / "Dockerfile").read_text(encoding="utf-8")

    declared = set(PATH_DEPENDENCY.findall(pyproject))
    copied = set(DOCKERFILE_COPY.findall(dockerfile))

    assert copied == declared, (
        f"{module.name}: pyproject.toml names {sorted(declared)}, the Dockerfile copies "
        f"{sorted(copied)}"
    )


@pytest.mark.parametrize(
    "module", modules_with_a_dockerfile(), ids=lambda p: p.name
)
def test_the_deploy_filter_watches_every_package_the_image_bakes_in(module: Path) -> None:
    """Baked in at build time means a merged package fix reaches production only if this module redeploys, so
    a filter missing a package is a fix that is merged, green, and not running."""
    # One workflow is not named after its module: the gateway's.
    workflow = WORKFLOWS / WORKFLOW_NAMES.get(module.name, f"deploy-{module.name}.yml")
    assert workflow.is_file(), f"{module.name} has a Dockerfile and no deploy workflow"

    declared = set(PATH_DEPENDENCY.findall((module / "pyproject.toml").read_text("utf-8")))
    paths = load(workflow)[True]["push"]["paths"]

    for package in declared:
        assert f"packages/{package}/**" in paths, (
            f"deploy-{module.name}.yml does not watch packages/{package}, which its image "
            "bakes in"
        )
