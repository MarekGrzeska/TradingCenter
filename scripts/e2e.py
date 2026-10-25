"""The terminal's end-to-end tests against a stack of their own: PostgreSQL on 55442 in memory, a workbench on 18030 and
Vite on 15173 (started by Playwright), none of them the dev stack's, so both can run at once. Every paid or external
address of that workbench leads to 127.0.0.1:9 (`modules/terminal/e2e/workbench.env`); nothing here pays for a model.

    pnpm e2e                    # from modules/terminal: start, seed, test, tear down
    pnpm e2e -- --keep          # leave the stack up afterwards, for `pnpm exec playwright test --ui`
    pnpm e2e -- -g ST-03        # anything after the script's own flags goes to `playwright test`
"""

from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
from collections.abc import Iterable, Mapping, Sequence

from dev import (
    CREATE_NEW_PROCESS_GROUP,
    LOOPBACK,
    MODULES,
    WINDOWS,
    _terminate_tree,
    fail,
    note,
    ok,
    resolve_command,
    say,
    wait_for_http,
)

TERMINAL = MODULES / "terminal"
WORKBENCH = MODULES / "workbench"
E2E = TERMINAL / "e2e"
COMPOSE = ["docker", "compose", "-f", str(E2E / "compose.e2e.yaml")]
WORKBENCH_PORT = 18030
PORTS = {WORKBENCH_PORT: "the e2e workbench", 15173: "the e2e terminal", 55442: "the e2e database"}

# What a child process needs from the parent's environment to find its tools and nothing more. An allowlist, not a
# denylist: an OPENAI_API_KEY exported in the developer's shell must not reach a workbench that would spend it.
INHERITED = {
    "PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "TEMP", "TMP", "HOME", "USERPROFILE",
    "APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "PROGRAMFILES", "PROGRAMFILES(X86)", "NUMBER_OF_PROCESSORS",
    "PROCESSOR_ARCHITECTURE", "LANG", "LC_ALL",
}


def read_env_file(text: str) -> dict[str, str]:
    """`KEY=value` lines, the value taken whole: a model catalogue is JSON with `=` and quotes a shell would mangle."""
    values: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key, value = stripped.split("=", 1)
            values[key.strip()] = value
    return values


def child_environment(parent: Mapping[str, str], settings: Mapping[str, str]) -> dict[str, str]:
    kept = {key: value for key, value in parent.items() if key.upper() in INHERITED or key.upper().startswith("UV_")}
    return kept | dict(settings)


def busy_ports(ports: Iterable[int]) -> list[int]:
    taken = []
    for port in ports:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            if probe.connect_ex((LOOPBACK, port)) == 0:
                taken.append(port)
    return taken


def parse_args(argv: Sequence[str] | None) -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--keep", action="store_true", help="leave the stack running after the tests")
    return parser.parse_known_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args, playwright_args = parse_args(argv)
    if playwright_args[:1] == ["--"]:
        playwright_args = playwright_args[1:]
    taken = busy_ports(PORTS)
    if taken:
        for port in taken:
            fail(f"port {port} ({PORTS[port]}) is in use — another e2e run, or something left over from one.")
        note(f"'{' '.join(COMPOSE)} down' removes a database left behind.")
        return 1

    settings = read_env_file((E2E / "workbench.env").read_text(encoding="utf-8"))
    environment = child_environment(os.environ, settings)
    log_path = E2E / "workbench.log"
    workbench: subprocess.Popen[str] | None = None
    log = None

    try:
        say("Starting the e2e database (empty, in memory)...")
        if subprocess.run([*COMPOSE, "up", "-d", "--wait"], check=False).returncode != 0:
            fail("the e2e database did not become healthy.")
            return 1

        say(f"Starting the e2e workbench on {WORKBENCH_PORT}; its output goes to {log_path}...")
        log = log_path.open("w", encoding="utf-8")
        # From e2e/, which has no .env: the workbench reads `.env` from where it starts, and modules/workbench/.env holds
        # the developer's real keys.
        workbench = subprocess.Popen(
            resolve_command(["uv", "run", "--project", str(WORKBENCH), "uvicorn", "--app-dir", str(WORKBENCH),
                             "workbench.app:app", "--host", LOOPBACK, "--port", str(WORKBENCH_PORT)]),
            cwd=E2E, env=environment, stdout=log, stderr=subprocess.STDOUT, text=True,
            start_new_session=not WINDOWS, creationflags=CREATE_NEW_PROCESS_GROUP if WINDOWS else 0,
        )
        if not wait_for_http(f"http://{LOOPBACK}:{WORKBENCH_PORT}/health", "the e2e workbench"):
            note(f"Its output: {log_path}")
            return 1
        ok("Workbench is up, every chain migrated.")

        seeded = subprocess.run(
            resolve_command(["uv", "run", "--project", str(WORKBENCH), "python", str(E2E / "seed.py")]),
            cwd=TERMINAL, env=environment | {"PYTHONPATH": str(WORKBENCH)}, check=False,
        )
        if seeded.returncode != 0:
            fail("seeding the e2e stack failed.")
            return 1

        say("Running Playwright...")
        tested = subprocess.run(resolve_command(["pnpm", "exec", "playwright", "test", *playwright_args]),
                                cwd=TERMINAL, check=False)
        return tested.returncode
    finally:
        if args.keep:
            note(f"Left running: workbench on {WORKBENCH_PORT}, database on 55442. Stop the workbench by hand, then "
                 f"'{' '.join(COMPOSE)} down'.")
        else:
            if workbench is not None:
                _terminate_tree(workbench)
            if log is not None:
                log.close()
            subprocess.run([*COMPOSE, "down"], check=False, capture_output=True)


if __name__ == "__main__":
    sys.exit(main())

