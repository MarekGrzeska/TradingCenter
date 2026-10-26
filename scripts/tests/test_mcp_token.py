"""operator-mcp-access — the helper Claude Code runs for a token: which API follows the address, and that it refuses
rather than waits when nobody is signed in. The token itself is MSAL's and Entra's."""

from __future__ import annotations

import pytest

import mcp_token


@pytest.mark.parametrize(
    ("url", "scope"),
    [
        ("https://api.example/trading/mcp", mcp_token.GATEWAY_SCOPE),
        ("https://api.example/market/mcp", mcp_token.WORKBENCH_SCOPE),
        ("https://api.example/team-tools/mcp", mcp_token.WORKBENCH_SCOPE),
        ("", mcp_token.WORKBENCH_SCOPE),
    ],
)
def test_the_api_follows_the_address(url: str, scope: str) -> None:
    assert mcp_token.scope_for(url) == scope


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
