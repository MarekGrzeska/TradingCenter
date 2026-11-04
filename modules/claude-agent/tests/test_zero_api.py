"""claude-agent-runtime: the session runs on the subscription only — every way Claude Code could be pointed at an API
account refuses the start, and names what it found."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from claude_agent import zero_api


def test_a_clean_configuration_passes(tmp_path: Path) -> None:
    assert zero_api.problem({}, [tmp_path / "missing.json"], tmp_path) is None


@pytest.mark.parametrize("name", zero_api.API_VARIABLES)
def test_a_key_in_the_environment_is_named(tmp_path: Path, name: str) -> None:
    assert name in (zero_api.problem({name: "sk-ant-x"}, [], tmp_path) or "")


def test_an_api_key_helper_in_any_settings_file_refuses(tmp_path: Path) -> None:
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"apiKeyHelper": "echo key"}))
    assert "apiKeyHelper" in (zero_api.problem({}, [settings], tmp_path) or "")


def test_a_stored_key_refuses(tmp_path: Path) -> None:
    (tmp_path / ".claude.json").write_text(json.dumps({"primaryApiKey": "sk-ant-x"}))
    assert "stored" in (zero_api.problem({}, [], tmp_path) or "")


def test_the_cli_says_ok_only_when_it_ran(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    for name in zero_api.API_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    assert zero_api.main([]) == 0
    assert capsys.readouterr().out.strip() == "zero-api: ok"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-x")
    assert zero_api.main([]) == zero_api.REFUSED
