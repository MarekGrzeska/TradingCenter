"""operator-mcp-access — the helper Claude Code runs for a token: which API each registered server asks for, and that it
refuses rather than waits when nobody is signed in. The token itself is MSAL's and Entra's."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

import mcp_token

INSTALLER = Path(__file__).resolve().parents[1] / "claude-mcp.sh"


def test_only_trading_mcp_is_registered_for_the_gateways_api(tmp_path: Path) -> None:
    calls = tmp_path / "calls"
    for tool in ("claude", "uv"):
        (tmp_path / tool).write_text(f'#!/bin/sh\necho "$@" >> {calls}\n')
        (tmp_path / tool).chmod(0o755)
    env = {**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}"}
    subprocess.run(["bash", str(INSTALLER), "install", "api.example", "tenant", "client"], env=env, check=True)

    registered = {}
    for line in calls.read_text().splitlines():
        if line.startswith("mcp add-json"):
            _, _, _, _, name, config = line.split(" ", 5)
            registered[name] = json.loads(config)
    apis = {name: config["headersHelper"].rsplit("--api ", 1)[1] for name, config in registered.items()}
    assert apis.pop("tc-trading") == "gateway"
    assert len(apis) == 8 and set(apis.values()) == {"workbench"}
    assert registered["tc-trading"]["url"] == "https://api.example/trading/mcp"


class _App:
    def __init__(self, accounts: list[dict], result: dict | None) -> None:
        self._accounts, self._result = accounts, result

    def get_accounts(self) -> list[dict]:
        return self._accounts

    def acquire_token_silent(self, scopes: list[str], account: dict) -> dict | None:
        return self._result


def test_a_cached_token_is_handed_over() -> None:
    app = _App([{"username": "op"}], {"access_token": "t"})
    assert mcp_token.silent_token(app, mcp_token.WORKBENCH_SCOPE) == "t"
    assert mcp_token.headers_for("t", edge_marker=False) == {"Authorization": "Bearer t"}


@pytest.mark.parametrize(("accounts", "result"), [([], None), ([{"username": "op"}], {"error": "invalid_grant"})])
def test_without_a_usable_sign_in_it_refuses_and_names_login(accounts: list[dict], result: dict | None) -> None:
    with pytest.raises(mcp_token.Refused, match="login"):
        mcp_token.silent_token(_App(accounts, result), mcp_token.WORKBENCH_SCOPE)
