"""claude-agent-runtime: the container's start, with stand-ins for tmux and the scheduler — an API key stops it before
anything else, and what the session reads is put back from the image on every start."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

MODULE = Path(__file__).parents[1]
pytestmark = pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("jq") is None or shutil.which("timeout") is None,
    reason="needs bash, jq and coreutils' timeout",
)


def _start(tmp_path: Path, **env: str) -> subprocess.CompletedProcess[str]:
    stubs = tmp_path / "stubs"
    stubs.mkdir(exist_ok=True)
    for name, body in {"tmux": "exit 1", "supercronic": "sleep 60"}.items():
        (stubs / name).write_text(f"#!/bin/sh\n{body}\n")
        (stubs / name).chmod(0o755)
    inherited = {k: v for k, v in os.environ.items() if not k.startswith("ANTHROPIC_")}
    environment = {
        **inherited,
        "PATH": f"{stubs}:{os.environ['PATH']}",
        "HOME": str(tmp_path),
        "CLAUDE_CONFIG_DIR": str(tmp_path / "config"),
        "AGENT_SRC": str(MODULE / "agent"),
        "AGENT_WORKDIR": str(tmp_path / "work"),
        "AGENT_PYTHON": sys.executable,
        "PYTHONPATH": str(MODULE),
        "API_HOST": "",
        "ENTRA_TENANT_ID": "t",
        "AGENT_ENTRA_CLIENT_ID": "c",
        **env,
    }
    return subprocess.run(
        ["timeout", "3", "bash", str(MODULE / "runtime" / "entrypoint.sh")],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def test_an_api_key_stops_the_start_and_is_named(tmp_path: Path) -> None:
    result = _start(tmp_path, ANTHROPIC_API_KEY="sk-ant-x")
    assert result.returncode == 64
    assert "ANTHROPIC_API_KEY" in result.stderr
    assert not (tmp_path / "work" / "CLAUDE.md").exists()


def test_the_image_puts_back_what_the_session_reads(tmp_path: Path) -> None:
    work = tmp_path / "work"
    (work / ".claude").mkdir(parents=True)
    (work / "CLAUDE.md").write_text("edited in the container")
    result = _start(tmp_path)
    assert (work / "CLAUDE.md").read_text() == (MODULE / "agent" / "CLAUDE.md").read_text()
    deny = (work / ".claude" / "settings.json").read_text().split('"deny"')[1]
    assert "mcp__tc-trading__place_order" in deny
    assert (work / ".mcp.json").exists()
    assert "instructions changed" in result.stdout
    assert "starting session (fresh)" in result.stdout


def test_what_the_agent_wrote_for_the_operator_lives_a_week(tmp_path: Path) -> None:
    out = tmp_path / "work" / "out"
    out.mkdir(parents=True)
    (out / "old.html").write_text("<p>old</p>")
    (out / "new.html").write_text("<p>new</p>")
    month_ago = (out / "old.html").stat().st_mtime - 30 * 24 * 3600
    os.utime(out / "old.html", (month_ago, month_ago))
    _start(tmp_path)
    assert not (out / "old.html").exists()
    assert (out / "new.html").exists()
