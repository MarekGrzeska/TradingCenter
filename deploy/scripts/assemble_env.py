"""Builds the server's `.env` from the names `deploy/env.required` lists, out of the JSON of GitHub's secrets and variables
(stdin), and prints it. Run by the deploy workflow on the runner; nothing here touches the network or writes a file, and a
refusal names the variable and never its value.

A value reaches Compose, which interpolates `$` in an unquoted `.env` line, so every value is written in single quotes —
and a value that cannot be (it holds a quote or a line break) is refused rather than escaped, because a secret that is
only right after escaping is a secret that will one day not be. A database password sits inside a connection URL, so it
is held to characters a URL carries as they are."""

from __future__ import annotations

import json
import os
import pathlib
import re
import sys

OPTIONAL = (
    "TELEGRAM_API_ID",
    "TELEGRAM_API_HASH",
    "TELEGRAM_SESSION_KEY",
    # The agent on the server (operator-agent-on-telegram): each has a working default when absent.
    "AGENT_TELEGRAM_OWNER_CHAT_ID",
    "AGENT_ACCOUNT_WRITES",
    "AGENT_CHECKINS",
    # The live account (live-account-trading): off, the usual state, unless LIVE_TRADING says `on` — then every one of
    # LIVE_REQUIRED must be there, and the switch for the agent's writes on it keeps its own default.
    "LIVE_TRADING",
    "AGENT_LIVE_ACCOUNT_WRITES",
    "LIVE_CAPITAL_API_KEY",
    "LIVE_CAPITAL_IDENTIFIER",
    "LIVE_CAPITAL_PASSWORD",
    "LIVE_GATEWAY_API_KEY",
    "LIVE_ACCOUNT_ID",
    "LIVE_ORDER_LIMITS",
)
LIVE_REQUIRED = (
    "LIVE_CAPITAL_API_KEY",
    "LIVE_CAPITAL_IDENTIFIER",
    "LIVE_CAPITAL_PASSWORD",
    "LIVE_GATEWAY_API_KEY",
    "LIVE_ACCOUNT_ID",
    "LIVE_ORDER_LIMITS",
)
# What the deploy adds itself when the live account is on: where the teams reach its tool server, and the profile that
# starts the two services at all.
LIVE_DERIVED = {"LIVE_TRADING_MCP_URL": "http://trading-mcp-live:80", "COMPOSE_PROFILES": "live"}
URL_SAFE = re.compile(r"^[A-Za-z0-9._~-]{16,}$")


class Refused(Exception):
    pass


def names_in(path: pathlib.Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.lstrip().startswith("#")]


def assemble(names: list[str], available: dict[str, str]) -> str:
    missing = [name for name in names if not available.get(name, "").strip()]
    if missing:
        raise Refused(f"missing from the environment's secrets and variables: {', '.join(missing)}")
    live = available.get("LIVE_TRADING", "").strip() == "on"
    if live:
        missing = [name for name in LIVE_REQUIRED if not available.get(name, "").strip()]
        if missing:
            raise Refused(f"LIVE_TRADING=on, and missing: {', '.join(missing)}")
        if available["LIVE_GATEWAY_API_KEY"] == available.get("GATEWAY_API_KEY"):
            # The live gateway's key opens real money; the demo one is held by more of the system than that should be.
            raise Refused("LIVE_GATEWAY_API_KEY must differ from GATEWAY_API_KEY")
    else:
        # Off means off: no live secret reaches the server, whatever the store still holds.
        available = {name: value for name, value in available.items() if name not in LIVE_REQUIRED}
    lines = []
    for name in [*names, *(n for n in OPTIONAL if available.get(n, "").strip())]:
        value = available[name]
        if "\n" in value or "\r" in value or "'" in value:
            raise Refused(f"{name} holds a quote or a line break, which a .env line cannot carry safely")
        if name.endswith("_DB_PASSWORD") and not URL_SAFE.match(value):
            raise Refused(f"{name} must be at least 16 characters of A-Z a-z 0-9 . _ ~ - (it sits in a URL)")
        lines.append(f"{name}='{value}'")
    if live:
        lines.extend(f"{name}='{value}'" for name, value in LIVE_DERIVED.items())
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if a != "--from-env"]
    from_env = "--from-env" in argv[1:]
    required = pathlib.Path(args[0]) if args else pathlib.Path("deploy/env.required")
    try:
        if from_env:
            # The workflow lists every name in its own `env:`, so this reads exactly what it was handed and nothing else.
            available = dict(os.environ)
        else:
            document = json.load(sys.stdin)
            # Variables first, secrets over them: a name in both is the secret's.
            available = {**document.get("vars", {}), **document.get("secrets", {})}
        sys.stdout.write(assemble(names_in(required), available))
    except (Refused, ValueError, OSError) as err:
        print(f"assemble_env: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
