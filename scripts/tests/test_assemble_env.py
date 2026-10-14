"""assemble_env: the server's `.env`, built from GitHub's secrets — refused rather than repaired."""

from __future__ import annotations

import importlib.util
import json
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
SCRIPT = ROOT / "deploy" / "scripts" / "assemble_env.py"
spec = importlib.util.spec_from_file_location("assemble_env", SCRIPT)
assert spec is not None and spec.loader is not None
assemble_env = importlib.util.module_from_spec(spec)
spec.loader.exec_module(assemble_env)

NAMES = assemble_env.names_in(ROOT / "deploy" / "env.required")


def full(**overrides: str) -> dict[str, str]:
    values = {name: "x" for name in NAMES}
    values.update({name: "a-database-password-ok" for name in NAMES if name.endswith("_DB_PASSWORD")})
    values.update(overrides)
    return values


def test_every_required_name_is_written_and_quoted() -> None:
    text = assemble_env.assemble(NAMES, full(AGENT_MODELS='[{"id":"m"}]'))
    assert "AGENT_MODELS='[{\"id\":\"m\"}]'\n" in text
    assert all(f"\n{name}='" in "\n" + text for name in NAMES)


def test_a_dollar_sign_survives_because_the_value_is_single_quoted() -> None:
    assert "CAPITAL_PASSWORD='pa$$word'\n" in assemble_env.assemble(NAMES, full(CAPITAL_PASSWORD="pa$$word"))


def test_the_optional_names_are_written_only_when_there_is_a_value() -> None:
    assert "ALERT_DESTINATION" not in assemble_env.assemble(NAMES, full())
    assert "ALERT_DESTINATION='ops'\n" in assemble_env.assemble(NAMES, full(ALERT_DESTINATION="ops"))


@pytest.mark.parametrize("value", ["", "   "])
def test_a_missing_or_blank_name_is_refused_by_name(value: str) -> None:
    with pytest.raises(assemble_env.Refused, match="GATEWAY_API_KEY"):
        assemble_env.assemble(NAMES, full(GATEWAY_API_KEY=value))


@pytest.mark.parametrize("value", ["it's", "two\nlines", "a\rb"])
def test_a_value_an_env_line_cannot_carry_is_refused(value: str) -> None:
    with pytest.raises(assemble_env.Refused, match="CAPITAL_API_KEY"):
        assemble_env.assemble(NAMES, full(CAPITAL_API_KEY=value))


@pytest.mark.parametrize("password", ["short", "has/a/slash-and-long-enough", "has@sign-and-long-enough-1"])
def test_a_database_password_a_url_cannot_carry_is_refused(password: str) -> None:
    with pytest.raises(assemble_env.Refused, match="AGENT_DB_PASSWORD"):
        assemble_env.assemble(NAMES, full(AGENT_DB_PASSWORD=password))


def test_a_refusal_does_not_print_the_value() -> None:
    with pytest.raises(assemble_env.Refused) as refused:
        assemble_env.assemble(NAMES, full(CAPITAL_API_KEY="the'secret"))
    assert "secret" not in str(refused.value)


def test_the_command_line_refuses_an_incomplete_document_and_prints_nothing_of_it() -> None:
    document = {"vars": {"IMAGE_PREFIX": "from-vars"}, "secrets": {"ACME_EMAIL": "a@b.test"}}
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(ROOT / "deploy" / "env.required")],
        input=json.dumps(document),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert result.stdout == ""
    assert "missing" in result.stderr
    assert "from-vars" not in result.stderr


def test_the_command_line_writes_a_complete_document() -> None:
    document = {"vars": {name: "v" for name in NAMES}, "secrets": {"IMAGE_PREFIX": "from-secrets"}}
    document["vars"].update({n: "a-database-password-ok" for n in NAMES if n.endswith("_DB_PASSWORD")})
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(ROOT / "deploy" / "env.required")],
        input=json.dumps(document),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "IMAGE_PREFIX='from-secrets'\n" in result.stdout


def test_the_workflow_hands_the_script_exactly_the_names_it_reads() -> None:
    """`toJSON(secrets)` would give the step the whole store; an explicit list is what a reviewer can read, and this keeps
    it the list `env.required` (plus the optional names) says it is."""
    import yaml

    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "deploy-vps.yml").read_text(encoding="utf-8"))
    steps = workflow["jobs"]["deploy"]["steps"]
    step = next(s for s in steps if s.get("name") == "Assemble the environment")
    assert set(step["env"]) == set(NAMES) | set(assemble_env.OPTIONAL)
    assert all(str(v).startswith(("${{ secrets.", "${{ vars.")) for v in step["env"].values())
    assert "toJSON(secrets)" not in (ROOT / ".github" / "workflows" / "deploy-vps.yml").read_text(encoding="utf-8")


def test_from_env_reads_the_environment_it_was_given() -> None:
    environment = {**{name: "x" for name in NAMES}, **{n: "a-database-password-ok" for n in NAMES if n.endswith("_DB_PASSWORD")}}
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--from-env", str(ROOT / "deploy" / "env.required")],
        env={**environment, "PATH": ""},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "GATEWAY_API_KEY='x'\n" in result.stdout
