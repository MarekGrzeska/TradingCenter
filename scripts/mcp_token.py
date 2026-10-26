# /// script
# requires-python = ">=3.12"
# dependencies = ["msal>=1.31", "msal-extensions>=1.2"]
# ///
"""The operator's token for production's tool surfaces, for Claude Code's `headersHelper` (`operator-mcp-access`).

    uv run --script scripts/mcp_token.py login   --tenant <id> --client-id <id>   # a browser, once
    uv run --script scripts/mcp_token.py headers --tenant <id> --client-id <id>   # what Claude Code runs

`headers` is silent or it fails: Claude Code gives a helper ten seconds and no screen, so a sign-in it would need is a
refusal naming `login`. Which API the token is for follows the address Claude Code is connecting to — trading-mcp's
(`/trading/`) takes the gateway's, every other surface the workbench's. The cache is the macOS keychain where there is
one, a file readable by the operator alone otherwise; nothing here prints a token anywhere but stdout."""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from pathlib import Path
from typing import Any

WORKBENCH_SCOPE = "api://tradingcenter-agent/access_as_user"
GATEWAY_SCOPE = "api://tradingcenter-capital-gateway/access_as_user"
SERVER_URL_VARIABLE = "CLAUDE_CODE_MCP_SERVER_URL"
CACHE = Path.home() / ".cache" / "tradingcenter" / "mcp-token-cache.bin"


class Refused(Exception):
    """Said on stderr, exit 1: Claude Code then shows the server as failed rather than connecting without a token."""


def scope_for(server_url: str) -> str:
    """trading-mcp checks tokens for the gateway's API; everything under the workbench, the workbench's."""
    return GATEWAY_SCOPE if "/trading/" in server_url else WORKBENCH_SCOPE


def headers_for(token: str, *, edge_marker: bool) -> dict[str, str]:
    """`edge_marker` is for a workbench run locally with SERVER_MODE, where no Caddy writes the marker the door reads."""
    headers = {"Authorization": f"Bearer {token}"}
    if edge_marker:
        headers["X-TC-Edge"] = "1"
    return headers


def silent_token(app: Any, scope: str) -> str:
    accounts = app.get_accounts()
    if not accounts:
        raise Refused(f"nobody is signed in: run `uv run --script {__file__} login` with the same tenant and client id")
    result = app.acquire_token_silent([scope], account=accounts[0])
    if not result or "access_token" not in result:
        detail = (result or {}).get("error_description", "no token in the cache and no refresh token that works")
        raise Refused(f"no token for {scope}: {detail}. Sign in again with `login`.")
    return result["access_token"]


def _application(tenant: str, client_id: str) -> Any:
    import msal
    from msal_extensions import FilePersistence, PersistedTokenCache, build_encrypted_persistence

    CACHE.parent.mkdir(parents=True, exist_ok=True)
    try:
        persistence = build_encrypted_persistence(str(CACHE))
    except Exception:  # noqa: BLE001 - no keychain or keyring here: the file, readable by the operator alone
        persistence = FilePersistence(str(CACHE))
        CACHE.touch(mode=0o600, exist_ok=True)
        os.chmod(CACHE, 0o600)
    return msal.PublicClientApplication(
        client_id,
        authority=f"https://login.microsoftonline.com/{tenant}",
        token_cache=PersistedTokenCache(persistence),
    )


def _claims(token: str) -> dict[str, Any]:
    """Read for the summary `login` prints, never trusted: the processes verify the signature themselves."""
    payload = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))


def login(app: Any) -> None:
    result = app.acquire_token_interactive([WORKBENCH_SCOPE], prompt="select_account")
    if "access_token" not in result:
        raise Refused(f"sign-in failed: {result.get('error_description', result.get('error'))}")
    for scope in (WORKBENCH_SCOPE, GATEWAY_SCOPE):
        claims = _claims(silent_token(app, scope))
        roles = ", ".join(claims.get("roles", [])) or "none — the door will refuse every tool"
        print(f"{scope}: {claims.get('preferred_username') or claims.get('upn')} · roles: {roles}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=("login", "headers", "logout"))
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--client-id", required=True)
    parser.add_argument("--edge-marker", action="store_true", help="add X-TC-Edge for a local SERVER_MODE workbench")
    args = parser.parse_args(argv)

    try:
        app = _application(args.tenant, args.client_id)
        if args.command == "login":
            login(app)
        elif args.command == "logout":
            for account in app.get_accounts():
                app.remove_account(account)
        else:
            scope = scope_for(os.environ.get(SERVER_URL_VARIABLE, ""))
            print(json.dumps(headers_for(silent_token(app, scope), edge_marker=args.edge_marker)))
    except Refused as refusal:
        print(f"mcp_token: {refusal}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
