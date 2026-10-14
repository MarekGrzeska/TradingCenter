"""Builds the server's `.env` from the names `deploy/env.required` lists, out of the JSON of GitHub's secrets and variables
(stdin), and prints it. Run by the deploy workflow on the runner; nothing here touches the network or writes a file, and a
refusal names the variable and never its value.

A value reaches Compose, which interpolates `$` in an unquoted `.env` line, so every value is written in single quotes —
and a value that cannot be (it holds a quote or a line break) is refused rather than escaped, because a secret that is
only right after escaping is a secret that will one day not be. A database password sits inside a connection URL, so it
is held to characters a URL carries as they are."""

from __future__ import annotations

import json
import pathlib
import re
import sys

OPTIONAL = ("ALERT_DESTINATION", "TELEGRAM_API_ID", "TELEGRAM_API_HASH", "TELEGRAM_SESSION")
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
    lines = []
    for name in [*names, *(n for n in OPTIONAL if available.get(n, "").strip())]:
        value = available[name]
        if "\n" in value or "\r" in value or "'" in value:
            raise Refused(f"{name} holds a quote or a line break, which a .env line cannot carry safely")
        if name.endswith("_DB_PASSWORD") and not URL_SAFE.match(value):
            raise Refused(f"{name} must be at least 16 characters of A-Z a-z 0-9 . _ ~ - (it sits in a URL)")
        lines.append(f"{name}='{value}'")
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    required = pathlib.Path(argv[1]) if len(argv) > 1 else pathlib.Path("deploy/env.required")
    try:
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
