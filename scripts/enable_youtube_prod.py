"""The operator's half of enabling the YouTube archive in production: hand the `youtube` database over to the workbench's
role, and put the two provider keys into Key Vault — from this machine's own files, never through a terminal or a
conversation. Terraform does the rest (`youtube_enabled`), and only after this has run.

    uv run python scripts/enable_youtube_prod.py              # a dry run: prints what it would do, with every value hidden
    uv run python scripts/enable_youtube_prod.py --apply --gemini-key-is-paid

Order, and why it is this one (`infra/variables.tf`, `youtube_enabled`):
  1. `terraform apply` with `youtube_enabled = false`    -> the database and the secret names exist, nothing is mounted
  2. this script with `--apply`                          -> the database is the workbench's, the keys have values
  3. `youtube_enabled = true`, `terraform apply`          -> the workbench is given the settings; one restart
An app setting that points at an empty secret is left in place as its own text, and a package that is given a database
it does not own refuses on its first CREATE TABLE — and takes the whole process with it. Doing the settings last is what
makes both impossible.

Steps are idempotent: the grant reassigns what is already owned to itself, and a secret set twice is a new version. The
temporary firewall rule (there is no standing one — `production-answers-from-outside`) is deleted in a `finally`.

Needs `az` signed in as the database's Entra administrator, and `psql` or Docker. Standard library only."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RESOURCE_GROUP = "rg-tradingcenter"
SERVER = "psql-tradingcenter"
DATABASE = "youtube"
# One App Service presents one identity since the modules became the workbench, so this is the role every one of its
# seven (now eight) databases is owned by.
ROLE = "app-tradingcenter-agent"
RULE = "tmp-operator"
GRANT_SQL = REPO_ROOT / "scripts" / "grant-schema-ownership.sql"
OSSRDBMS = "https://ossrdbms-aad.database.windows.net"

# Local setting -> Key Vault secret, the names `infra/key-vault.tf` declares.
SECRETS: Mapping[str, str] = {
    "YOUTUBE_DATA_API_KEY": "youtube-data-api-key",
    "YOUTUBE_GEMINI_API_KEY": "gemini-api-key",
}

Run = Callable[[Sequence[str], Mapping[str, str] | None], str]


class Refusal(Exception):
    """Something this script will not do, said so a person can act on it."""


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        raise Refusal(f"{path} does not exist")
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        text = line.strip()
        if text and not text.startswith("#") and "=" in text:
            key, _, value = text.partition("=")
            values[key.strip()] = value.strip().strip("\"'")
    return values


def secrets_from(env: Mapping[str, str]) -> dict[str, str]:
    """The Key Vault secret name -> value, refused if any is missing or still a placeholder."""
    found: dict[str, str] = {}
    for setting, secret in SECRETS.items():
        value = env.get(setting, "")
        if not value:
            raise Refusal(
                f"{setting} is empty in the workbench .env — there is nothing to put in the secret {secret}"
            )
        found[secret] = value
    return found


def redact(command: Sequence[str], values: Sequence[str]) -> str:
    text = " ".join(command)
    for value in values:
        text = text.replace(value, "<hidden>")
    return text


def real_run(command: Sequence[str], env: Mapping[str, str] | None = None) -> str:
    executable = shutil.which(command[0]) or command[0]
    # MSYS_NO_PATHCONV: Git Bash rewrites anything that looks like a path, and `/subscriptions/...` does.
    merged = {**os.environ, "MSYS_NO_PATHCONV": "1", **(env or {})}
    done = subprocess.run(
        [executable, *command[1:]], env=merged, capture_output=True, text=True, check=False
    )
    if done.returncode != 0:
        # stderr only, and trimmed: a CLI's error can quote a request, and nothing here sends a secret on a command line.
        raise Refusal(
            f"`{command[0]} {command[1] if len(command) > 1 else ''}` failed: {done.stderr.strip()[:400]}"
        )
    return done.stdout.strip()


@dataclass
class Plan:
    vault: str
    admin: str
    ip: str
    secrets: dict[str, str]
    psql: list[str]


def build_psql(token: str, admin: str, fqdn: str) -> tuple[list[str], dict[str, str]]:
    """`psql` when it is on the machine, Docker when it is not — the token goes in the environment, never an argument."""
    dsn = f"host={fqdn} port=5432 dbname={DATABASE} user={admin} sslmode=require"
    env = {"PGPASSWORD": token}
    if shutil.which("psql"):
        return ["psql", dsn, "-v", f"role={ROLE}", "-f", str(GRANT_SQL)], env
    if shutil.which("docker"):
        return [
            "docker", "run", "--rm", "-e", "PGPASSWORD", "-v", f"{GRANT_SQL.parent}:/s:ro", "postgres:17-alpine",
            "psql", dsn, "-v", f"role={ROLE}", "-f", "/s/grant-schema-ownership.sql",
        ], env  # fmt: skip
    raise Refusal(
        "neither psql nor docker is on this machine — one of them is needed to hand the database over"
    )


def detect_ip() -> str:
    with urllib.request.urlopen("https://api.ipify.org", timeout=10) as response:
        return response.read().decode().strip()


def execute(
    args: argparse.Namespace, run: Run = real_run, ip_of: Callable[[], str] = detect_ip
) -> int:
    env = read_env(Path(args.env))
    secrets = secrets_from(env)
    hidden = list(secrets.values())

    def say(text: str) -> None:
        print(redact([text], hidden))

    say(
        f"Secrets to write ({len(secrets)}): "
        + ", ".join(f"{name} ({len(value)} chars)" for name, value in secrets.items())
    )
    if not args.apply:
        say("DRY RUN — nothing is changed. Planned, in this order:")
        for step in (
            f"find the Key Vault in {RESOURCE_GROUP}",
            f"open a temporary firewall rule `{RULE}` on {SERVER} for this machine's address",
            f"psql -> {DATABASE}: grant-schema-ownership.sql with role={ROLE}",
            f"delete the rule `{RULE}` (also if the step above fails)",
            "write each secret to Key Vault from a temporary file, deleted at once",
            "tell you to set youtube_enabled = true and apply",
        ):
            say(f"  - {step}")
        return 0
    if not args.gemini_key_is_paid:
        raise Refusal(
            "the Gemini key is sent every film's address, and the free tier lets Google use what it is sent: production "
            "needs a paid key. Confirm it is one with --gemini-key-is-paid"
        )

    vault = run(
        ["az", "keyvault", "list", "-g", RESOURCE_GROUP, "--query", "[0].name", "-o", "tsv"], None
    )
    if not vault:
        raise Refusal(
            f"no Key Vault in {RESOURCE_GROUP} — is `az` signed in to the right subscription?"
        )
    admin = run(
        ["az", "ad", "signed-in-user", "show", "--query", "userPrincipalName", "-o", "tsv"], None
    )
    fqdn = run(["az", "postgres", "flexible-server", "show", "-g", RESOURCE_GROUP, "-n", SERVER,
                "--query", "fullyQualifiedDomainName", "-o", "tsv"], None)  # fmt: skip
    ip = args.ip or ip_of()
    say(f"Key Vault {vault}; administrator {admin}; this machine is {ip}")

    if not args.skip_grant:
        run(["az", "postgres", "flexible-server", "firewall-rule", "create", "-g", RESOURCE_GROUP, "-n", SERVER,
             "--rule-name", RULE, "--start-ip-address", ip, "--end-ip-address", ip], None)  # fmt: skip
        try:
            token = run(
                [
                    "az",
                    "account",
                    "get-access-token",
                    "--resource",
                    OSSRDBMS,
                    "--query",
                    "accessToken",
                    "-o",
                    "tsv",
                ],
                None,
            )
            command, psql_env = build_psql(token, admin, fqdn)
            output = run(command, psql_env | {"PGPASSWORD": token})
            say(output[-600:])
            say(f"{DATABASE} handed over to {ROLE}")
        finally:
            run(["az", "postgres", "flexible-server", "firewall-rule", "delete", "-g", RESOURCE_GROUP, "-n", SERVER,
                 "--rule-name", RULE, "--yes"], None)  # fmt: skip
            say(f"firewall rule {RULE} deleted")

    if not args.skip_secrets:
        for name, value in secrets.items():
            # A file, not `--value`: an argument is visible to every process on the machine while it runs.
            with tempfile.TemporaryDirectory(prefix="tc-secret-") as folder:
                path = Path(folder) / "value"
                path.write_text(value, encoding="utf-8", newline="")
                run(["az", "keyvault", "secret", "set", "--vault-name", vault, "--name", name, "--file", str(path),
                     "--encoding", "utf-8", "--query", "id", "-o", "tsv"], None)  # fmt: skip
            say(f"secret {name} written")

    say(
        "Done. Next: set youtube_enabled = true in infra/terraform.tfvars and `terraform apply` (one restart),"
    )
    say("then follow the deployment (deploy-watch) and read /youtube/state (prod-health).")
    return 0


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument(
        "--apply",
        action="store_true",
        help="do it; without this the script only says what it would do",
    )
    p.add_argument(
        "--gemini-key-is-paid",
        action="store_true",
        help="confirm the Gemini key is not a free-tier one",
    )
    p.add_argument(
        "--env",
        default=str(REPO_ROOT / "modules" / "workbench" / ".env"),
        help="where the two keys are read from",
    )
    p.add_argument("--ip", help="this machine's public address (default: asked of api.ipify.org)")
    p.add_argument("--skip-grant", action="store_true", help="only write the secrets")
    p.add_argument("--skip-secrets", action="store_true", help="only hand the database over")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    try:
        return execute(parser().parse_args(argv))
    except Refusal as err:
        print(f"refused: {err}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
