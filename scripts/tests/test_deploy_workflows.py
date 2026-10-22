"""The deploy workflow read as data. One workflow since move-from-azure-to-vps: `deploy-vps.yml` builds all three images and
both front ends and hands them to the server, so the lessons the seven Azure ones learned live in one place."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO / ".github" / "workflows"
DEPLOY = WORKFLOWS / "deploy-vps.yml"
MODULES = REPO / "modules"


# `dict[Any, Any]`, not `dict[str, Any]`: `on:` parses as the boolean True under YAML 1.1.
def load(path: Path) -> dict[Any, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_there_is_one_deploy_workflow() -> None:
    assert sorted(p.name for p in WORKFLOWS.glob("deploy-*.yml")) == ["deploy-vps.yml"]
    assert not list(WORKFLOWS.glob("_deploy-*.yml")), "the shared Azure workflow went with Azure"


# P5, 2 September 2026: until then a push to `main` ran `checks` and every deploy in the same second, so a merge with a
# red test was serving before CI had finished saying so. Measured twice that day, on #233 and #234.
def test_nothing_deploys_on_the_push_itself() -> None:
    on = load(DEPLOY)[True]
    assert "push" not in on and "pull_request" not in on
    assert on["workflow_run"]["workflows"] == ["checks"]
    assert on["workflow_run"]["types"] == ["completed"]
    # `infra/vps` until that branch is merged (tasks.md 9.6), and `main` after.
    assert on["workflow_run"]["branches"] in (["infra/vps"], ["main"])
    assert "workflow_dispatch" in on, "the operator's door around the gate"


def test_the_deploy_waits_for_a_green_checks_run() -> None:
    """`completed` fires on failure and on cancellation too — a superseded run is cancelled, and its commit is covered
    by the next green one's diff, which is the gate's whole reason for diffing from the last green."""
    condition = load(DEPLOY)["jobs"]["deploy"]["if"]
    assert "workflow_run.conclusion == 'success'" in condition
    assert "workflow_dispatch" in condition


def test_the_gate_may_list_the_checks_runs_and_the_job_may_push_images() -> None:
    permissions = load(DEPLOY).get("permissions") or {}
    assert permissions.get("actions") == "read"
    assert permissions.get("packages") == "write"
    assert "id-token" not in permissions, "nothing exchanges an OIDC token any more"


def test_never_cancels_a_deploy_mid_flight() -> None:
    assert load(DEPLOY)["concurrency"]["cancel-in-progress"] is False


def test_the_checked_commit_is_the_one_built_never_the_branch_head() -> None:
    """`github.sha` under `workflow_run` is whatever the branch points at now — the checked commit only until two
    pushes land close together. Every checkout, tag and probe takes the gate's `sha` output instead."""
    jobs = load(DEPLOY)["jobs"]
    assert jobs["deploy"]["needs"] == "gate"
    deploy_section = DEPLOY.read_text(encoding="utf-8").split("  deploy:\n", 1)[1]
    assert "${{ github.sha }}" not in deploy_section
    assert "needs.gate.outputs.sha" in deploy_section


def test_every_image_is_tagged_with_the_commit_and_never_latest() -> None:
    builds = [s for s in load(DEPLOY)["jobs"]["deploy"]["steps"] if str(s.get("uses", "")).startswith("docker/build-push-action")]
    assert len(builds) == 3
    for step in builds:
        assert step["with"]["tags"].endswith(":${{ needs.gate.outputs.sha }}")
        assert "latest" not in step["with"]["tags"]


PATH_DEPENDENCY = re.compile(r'^(tc-[a-z-]+)\s*=\s*\{\s*path\s*=\s*"\.\./\.\./packages/', re.MULTILINE)
DOCKERFILE_COPY = re.compile(r"^COPY packages/(tc-[a-z-]+) ", re.MULTILINE)


def modules_with_a_dockerfile() -> list[Path]:
    return sorted(p for p in MODULES.iterdir() if (p / "Dockerfile").is_file())


@pytest.mark.parametrize("module", modules_with_a_dockerfile(), ids=lambda p: p.name)
def test_the_image_copies_exactly_the_packages_the_module_takes(module: Path) -> None:
    """A package in `pyproject.toml` and not in the Dockerfile is a build that fails; one the other way round is a layer
    invalidated by source this image never installs."""
    declared = set(PATH_DEPENDENCY.findall((module / "pyproject.toml").read_text(encoding="utf-8")))
    copied = set(DOCKERFILE_COPY.findall((module / "Dockerfile").read_text(encoding="utf-8")))
    assert copied == declared, f"{module.name}: pyproject.toml names {sorted(declared)}, the Dockerfile copies {sorted(copied)}"


@pytest.mark.parametrize("module", modules_with_a_dockerfile(), ids=lambda p: p.name)
def test_every_image_is_built_and_watched_by_the_deploy(module: Path) -> None:
    """Baked in at build time means a merged fix reaches the server only if the deploy sees it changed."""
    text = DEPLOY.read_text(encoding="utf-8")
    assert f"file: modules/{module.name}/Dockerfile" in text
    gate = load(DEPLOY)["jobs"]["gate"]["steps"][-1]["env"]["PATHS"].split()
    assert f"modules/{module.name}" in gate
    assert "packages" in gate, "every package is baked into some image"
