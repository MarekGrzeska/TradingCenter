"""The script that touches production secrets, tested at what it must never do: print a value, put one on a command line,
or leave the firewall open. The commands are recorded, not run."""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

import enable_youtube_prod as script

DATA_KEY = "AIzaSy-data-api-secret-111"
GEMINI_KEY = "AIzaSy-gemini-secret-222"


@pytest.fixture
def env_file(tmp_path):
    path = tmp_path / ".env"
    path.write_text(
        f"YOUTUBE_DATA_API_KEY={DATA_KEY}\nYOUTUBE_GEMINI_API_KEY='{GEMINI_KEY}'\n",
        encoding="utf-8",
    )
    return path


def args(env_file, **overrides) -> argparse.Namespace:
    base = {"apply": True, "gemini_key_is_paid": True, "env": str(env_file), "ip": "203.0.113.7",
            "skip_grant": False, "skip_secrets": False}  # fmt: skip
    return argparse.Namespace(**(base | overrides))


class Recorder:
    def __init__(self, fail_on: str | None = None) -> None:
        self.calls: list[list[str]] = []
        self.written: dict[str, str] = {}
        self._fail_on = fail_on

    def __call__(self, command, env=None) -> str:
        self.calls.append(list(command))
        if self._fail_on and command[0] == self._fail_on:
            raise script.Refusal("boom")
        if command[:3] == ["az", "keyvault", "list"]:
            return "kv-tradingctr-test"
        if "signed-in-user" in command:
            return "operator@example.com"
        if command[:3] == ["az", "postgres", "flexible-server"] and "show" in command:
            return "psql-tradingcenter.postgres.database.azure.com"
        if "get-access-token" in command:
            return "entra-token"
        if command[:4] == ["az", "keyvault", "secret", "set"]:
            # The value is read from the temporary file while it still exists, as the CLI would.
            name, path = command[command.index("--name") + 1], command[command.index("--file") + 1]
            self.written[name] = Path(path).read_text(encoding="utf-8")
        return ""

    def verbs(self) -> list[str]:
        return [" ".join(call[:4]) for call in self.calls]


@pytest.fixture(autouse=True)
def tooling(monkeypatch):
    monkeypatch.setattr(
        script.shutil, "which", lambda name: f"/usr/bin/{name}" if name == "psql" else None
    )


def test_a_dry_run_runs_nothing_and_shows_no_value(env_file, capsys) -> None:
    recorder = Recorder()

    assert script.execute(args(env_file, apply=False), run=recorder) == 0

    shown = capsys.readouterr().out
    assert recorder.calls == []
    assert DATA_KEY not in shown and GEMINI_KEY not in shown
    assert "DRY RUN" in shown and "youtube-data-api-key" in shown


def test_it_will_not_apply_without_the_word_that_the_gemini_key_is_paid(env_file) -> None:
    recorder = Recorder()

    with pytest.raises(script.Refusal, match="paid key"):
        script.execute(args(env_file, gemini_key_is_paid=False), run=recorder)

    assert recorder.calls == []


def test_an_empty_key_is_refused_before_anything_is_touched(tmp_path) -> None:
    path = tmp_path / ".env"
    path.write_text(f"YOUTUBE_DATA_API_KEY={DATA_KEY}\nYOUTUBE_GEMINI_API_KEY=\n", encoding="utf-8")
    recorder = Recorder()

    with pytest.raises(script.Refusal, match="YOUTUBE_GEMINI_API_KEY"):
        script.execute(args(path), run=recorder)

    assert recorder.calls == []


def test_the_database_is_handed_over_inside_a_firewall_rule_and_the_secrets_arrive_by_file(
    env_file, capsys
) -> None:
    recorder = Recorder()

    assert script.execute(args(env_file), run=recorder) == 0

    verbs = recorder.verbs()
    opened = verbs.index("az postgres flexible-server firewall-rule")
    grant = next(i for i, call in enumerate(recorder.calls) if call[0] == "psql")
    closed = len(verbs) - 1 - verbs[::-1].index("az postgres flexible-server firewall-rule")
    assert opened < grant < closed
    assert "delete" in recorder.calls[closed]
    assert recorder.written == {"youtube-data-api-key": DATA_KEY, "gemini-api-key": GEMINI_KEY}
    everything = " ".join(" ".join(call) for call in recorder.calls) + capsys.readouterr().out
    assert DATA_KEY not in everything and GEMINI_KEY not in everything, (
        "a value on a command line or on the screen"
    )
    assert "entra-token" not in everything, (
        "the database token travels in the environment, not an argument"
    )


def test_a_failed_grant_still_closes_the_firewall_and_writes_no_secret(env_file) -> None:
    recorder = Recorder(fail_on="psql")

    with pytest.raises(script.Refusal):
        script.execute(args(env_file), run=recorder)

    assert "delete" in recorder.calls[-1] and "firewall-rule" in recorder.calls[-1]
    assert recorder.written == {}


def test_the_database_token_reaches_psql_through_the_environment(env_file) -> None:
    command, psql_env = script.build_psql("entra-token", "operator@example.com", "host.example")

    assert psql_env == {"PGPASSWORD": "entra-token"}
    assert "entra-token" not in " ".join(command)


def test_handing_the_database_over_does_not_wait_on_a_word_about_the_key(env_file) -> None:
    """The paid-key confirmation guards the secrets only: the grant has nothing to do with Gemini."""
    recorder = Recorder()

    assert script.execute(args(env_file, gemini_key_is_paid=False, skip_secrets=True), run=recorder) == 0

    assert recorder.written == {}
    assert any(call[0] == "psql" for call in recorder.calls)
