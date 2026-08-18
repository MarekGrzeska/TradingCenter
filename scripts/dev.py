"""Everything the terminal needs, in the order it needs it — on every platform, once.

This replaces `dev.sh` and `dev.ps1`, which were the same script written twice and drifted
three times before 18 August 2026 — each time in one of them and not the other, each time
found by a symptom rather than by a check. The last of the three left `dev.ps1` starting
`teams-mcp` and immediately forgetting it: no log, no supervision, and a process surviving
only because the port sweep at the end happened to leave it alone.

All of that drift lived in the service table, not in the process plumbing, so the table is
data here and there is one copy of it. `dev.sh` and `dev.ps1` still work; they pass their
arguments to this file.

    uv run python scripts/dev.py                 # everything
    uv run python scripts/dev.py --no-terminal   # back end only, e.g. to run the live tests

Nothing depends on this script: every module still starts on its own with the command in
its README.
"""

from __future__ import annotations

import argparse
import io
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MODULES = REPO_ROOT / "modules"

# 127.0.0.1 rather than "localhost": uvicorn binds IPv4 loopback, and on a machine where
# "localhost" resolves to ::1 first the wait below would never succeed.
LOOPBACK = "127.0.0.1"

# How long a service gets to answer its health path. A cold `uv run` resolving dependencies
# is the usual slow part.
WAIT_SECONDS = 120

WINDOWS = os.name == "nt"

# Windows consoles default to the ANSI codepage, which turns every em dash in the reasons
# below into a replacement character. Reconfiguring here rather than asking whoever runs
# this to set PYTHONUTF8.
for _stream in (sys.stdout, sys.stderr):
    if isinstance(_stream, io.TextIOWrapper):
        _stream.reconfigure(encoding="utf-8", errors="replace")
# Absent off Windows, so read once rather than referenced inside a branch pyright still
# checks for the other platform.
CREATE_NEW_PROCESS_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)


# --- the service table ---------------------------------------------------------------
#
# One row per service, in start order. `why` is the part that used to live as a comment
# beside a hand-written start block in two files — the reason this row is where it is. It
# stays with the row so moving the row moves the reason, and `--explain` prints it.


@dataclass(frozen=True)
class Service:
    name: str
    module: str
    port: int
    command: tuple[str, ...]
    log_prefix: str
    colour: str
    why: str
    health_path: str | None = None
    # Only the terminal has one, for a machine with npm and no pnpm.
    fallback_command: tuple[str, ...] = ()

    @property
    def directory(self) -> Path:
        return MODULES / self.module

    @property
    def url(self) -> str:
        return f"http://{LOOPBACK}:{self.port}"

    @property
    def health_url(self) -> str | None:
        return None if self.health_path is None else f"{self.url}{self.health_path}"


BLUE, MAGENTA, CYAN, YELLOW, GREEN, RED, DIM, RESET = (
    "\033[34m",
    "\033[35m",
    "\033[36m",
    "\033[33m",
    "\033[32m",
    "\033[31m",
    "\033[2m",
    "\033[0m",
)
# The six basic colours were spoken for at six services. Bright green for trading-mcp is
# deliberately a shade of market-mcp's own — the two tool servers read as a pair in the log,
# which is what they are — and bright magenta went to teams-mcp, the third tool server and
# the only one carrying somebody's own credential rather than a module's.
BRIGHT_BLUE, BRIGHT_GREEN, BRIGHT_MAGENTA = "\033[94m", "\033[92m", "\033[95m"

SERVICES: tuple[Service, ...] = (
    Service(
        name="capital-gateway",
        module="capital-gateway",
        port=8010,
        command=("uv", "run", "uvicorn", "capital_gateway.app:app", "--reload", "--port", "8010"),
        log_prefix="gateway ",
        colour=BLUE,
        # "/" specifically — every other route needs X-Gateway-Key, and "/" is the one
        # exception carved out for exactly this kind of health probe.
        health_path="/",
        why="First: everything below either calls it or calls something that does.",
    ),
    Service(
        name="market-data",
        module="market-data",
        port=8020,
        command=("uv", "run", "uvicorn", "market_data.app:app", "--reload", "--port", "8020"),
        log_prefix="archive ",
        colour=MAGENTA,
        health_path="/health",
        why=(
            "After the gateway: it opens a subscription per tracked pair the moment it "
            "starts, so a gateway not listening yet costs it a round of backoff."
        ),
    ),
    Service(
        name="market-mcp",
        module="market-mcp",
        port=8040,
        # No `--reload`: unlike the uvicorn services this one is not started through
        # uvicorn's CLI (`server.py`'s caller-identity wrapper needs the ASGI app built in
        # Python first), so a code change here needs a manual restart.
        command=("uv", "run", "python", "-m", "market_mcp", "http"),
        log_prefix="mcp     ",
        colour=GREEN,
        health_path="/health",
        why="After market-data, whose contract it reads.",
    ),
    Service(
        name="trading-mcp",
        module="trading-mcp",
        port=8060,
        # No `--reload`, same reason as market-mcp's.
        command=("uv", "run", "python", "-m", "trading_mcp"),
        log_prefix="trading ",
        colour=BRIGHT_GREEN,
        health_path="/health",
        why=(
            "After the gateway, and not as a preference: `__main__.py` asks "
            "GET /capabilities and refuses to open a port unless the answer says demo "
            "(specs/trading-mcp-upstream-access). A gateway not answering yet is therefore "
            "a module that exits rather than one that retries, which the supervisor below "
            "reports as 'a service exited' — and it would be telling the truth."
        ),
    ),
    Service(
        name="teams",
        module="teams",
        port=8050,
        command=("uv", "run", "uvicorn", "teams.app:app", "--reload", "--port", "8050"),
        log_prefix="teams   ",
        colour=BRIGHT_BLUE,
        health_path="/health",
        why=(
            "After market-mcp and trading-mcp, whose tools its runs assign — and before "
            "teams-mcp, whose tools *are* teams' catalogue. Not before the agent for any "
            "reason of its own: the two are siblings, and what puts teams first is "
            "teams-mcp standing between them."
        ),
    ),
    Service(
        name="teams-mcp",
        module="teams-mcp",
        port=8070,
        command=("uv", "run", "python", "-m", "teams_mcp"),
        log_prefix="teamsmcp",
        colour=BRIGHT_MAGENTA,
        health_path="/health",
        why=(
            "After teams, because its tools are teams' catalogue — though it starts happily "
            "without it and reports the outage per call rather than refusing to run, which "
            "is market-mcp's shape and not trading-mcp's. Before the agent, which mounts "
            "its tools: that is for a log reading in the direction the arrows point rather "
            "than for correctness."
        ),
    ),
    Service(
        name="agent",
        module="agent",
        port=8030,
        command=("uv", "run", "uvicorn", "agent.app:app", "--reload", "--port", "8030"),
        log_prefix="agent   ",
        colour=YELLOW,
        health_path="/health",
        why=(
            "Last among the back ends: nothing else calls it, so nothing waits on it. It "
            "calls all three tool servers, and each tool list is read on the first turn "
            "that wants one — a server still coming up would mean a turn answered without "
            "those tools rather than an error anyone would notice."
        ),
    ),
    Service(
        name="terminal",
        module="terminal",
        port=5173,
        command=("pnpm", "exec", "vite", "--port", "5173", "--strictPort"),
        fallback_command=("npx", "vite", "--port", "5173", "--strictPort"),
        log_prefix="terminal",
        colour=CYAN,
        # Not waited for: vite is ready in a moment and nothing downstream needs it.
        health_path=None,
        why=(
            "Last, because its charts read the archive — starting it first fills the "
            "console with proxy errors that mean nothing."
        ),
    ),
)

# Modules whose migrations are applied before anything starts. Redundant with the startup
# migration each of them now runs under an advisory lock, and kept because it fails here
# with a readable error instead of inside a lifespan that is holding a lock.
MIGRATING_MODULES = ("market-data", "agent", "teams")

# The further logical databases in the same container, created here if missing rather than
# through docker-entrypoint-initdb.d — that only runs against an empty volume, so it would
# never fire for anyone holding a tradingcenter-db-data from before these modules existed.
LOGICAL_DATABASES = ("agent", "teams")


# --- reading .env files --------------------------------------------------------------


def env_value(text: str, key: str) -> str | None:
    """The first `KEY=value` in an `.env`, or None. Not a parser — a reader for four keys."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(f"{key}="):
            return stripped[len(key) + 1 :].strip()
    return None


def database_host(text: str) -> str | None:
    """The host out of `DATABASE_URL`, between the optional `user:pass@` and the port."""
    url = env_value(text, "DATABASE_URL")
    if not url:
        return None
    match = re.match(r"^[a-z+]*://(?:[^@/]*@)?([^:/?]*)", url)
    return match.group(1) if match else None


def is_loopback(host: str | None) -> bool:
    return not host or host == "localhost" or host.startswith("127.") or host == "::1"


# --- the checks that run before anything starts --------------------------------------
#
# Collected and reported together. Finding out about a missing `.env` after two services
# are running means killing them to fix one line.

# Which `.env` each module needs, and what is missing from it if it is absent. market-mcp
# and teams-mcp are not here on purpose: every setting they read has a working loopback
# default (`config.py`), unlike the modules holding real credentials.
REQUIRED_ENV: tuple[tuple[str, str], ...] = (
    ("capital-gateway", "copy .env.example and fill in demo credentials"),
    ("market-data", "copy .env.example; the defaults match compose.yaml"),
    ("agent", "copy .env.example and fill in OPENAI_API_KEY"),
    # teams needs a key and a MODELS catalogue: config.py refuses to build Settings without
    # either, so the module would exit at import rather than start and misbehave.
    (
        "teams",
        "copy .env.example and fill in OPENAI_API_KEY (MODELS has a working default there)",
    ),
    # trading-mcp cannot fall back the way market-mcp does: `config.py` requires the
    # gateway's caller key, and the gateway checks it on loopback too.
    (
        "trading-mcp",
        "copy .env.example and set CAPITAL_GATEWAY_API_KEY to the gateway's own GATEWAY_API_KEY",
    ),
)


@dataclass
class Environment:
    """Everything the checks read, injected so each refusal has a test."""

    which: Callable[[str], str | None]
    read_env: Callable[[str], str | None]
    port_in_use: Callable[[int], bool]
    port_owner: Callable[[int], str] = lambda _: ""
    docker_daemon_answers: Callable[[], bool] = lambda: True
    node_modules_present: Callable[[], bool] = lambda: True


def preflight(env: Environment, *, start_terminal: bool) -> list[str]:
    """Every reason not to start, in one list. Empty means go."""
    problems: list[str] = []

    if not env.which("uv"):
        problems.append(
            "uv is not on PATH (runs every Python service) — https://docs.astral.sh/uv/"
        )

    # The database lives in a container, so Docker runs the stack, not only market-data's
    # tests (openspec/changes/local-dev-database-in-docker).
    if not env.which("docker"):
        problems.append(
            "docker is not on PATH (runs the database, compose.yaml) "
            "— https://docs.docker.com/get-docker/"
        )
    elif not env.docker_daemon_answers():
        problems.append(
            "docker is installed but the daemon is not answering — start Docker Desktop "
            "(or the service)"
        )

    for module, remedy in REQUIRED_ENV:
        if env.read_env(module) is None:
            problems.append(f"modules/{module}/.env is missing — {remedy}")

    if start_terminal:
        if not env.which("pnpm") and not env.which("npm"):
            problems.append(
                "neither pnpm nor npm is on PATH (runs the terminal) — "
                "https://pnpm.io/installation"
            )
        if not env.node_modules_present():
            installer = "pnpm install" if env.which("pnpm") or not env.which("npm") else "npm install"
            problems.append(
                f"modules/terminal/node_modules is missing — run '{installer}' in modules/terminal"
            )

    problems += _port_problems(env, start_terminal=start_terminal)
    problems += _database_host_problems(env)
    problems += _gateway_key_problems(env)
    return problems


def _port_problems(env: Environment, *, start_terminal: bool) -> list[str]:
    """A taken port is the commonest reason a run appears to hang.

    The new process cannot bind, and the wait then watches somebody else's service. Tested
    by connecting rather than by asking who owns it: a service left over from a previous run
    does not always show up under the current user.
    """
    problems: list[str] = []
    for service in services_to_start(start_terminal=start_terminal):
        if env.port_in_use(service.port):
            owner = env.port_owner(service.port)
            problems.append(
                f"port {service.port} is already in use{owner} — stop it, or it is a "
                f"leftover run ({service.name})"
            )
    return problems


def _database_host_problems(env: Environment) -> list[str]:
    """The quiet disaster: an `.env` still pointing at the Azure server.

    `config.py` refuses the same thing at startup — no DATABASE_USER means loopback only —
    and repeating it here refuses earlier, before anything has been launched, naming the
    file to fix.
    """
    problems: list[str] = []
    for module in ("market-data", "agent", "teams"):
        text = env.read_env(module)
        if text is None:
            continue
        host = database_host(text)
        if not is_loopback(host):
            problems.append(
                f"modules/{module}/.env's DATABASE_URL points at '{host}' — local runs use "
                "the compose.yaml container (localhost), never a remote database"
            )
    return problems


def _gateway_key_problems(env: Environment) -> list[str]:
    """The two halves of one credential, in two files.

    The gateway checks `X-Gateway-Key` on every caller including loopback, and trading-mcp
    asks it about the account *before* it opens a port — so a mismatch here is not a failed
    tool call later, it is a module that exits during start-up and takes the whole run down
    with it. Cheap to compare, and the message is the fix.
    """
    gateway_env = env.read_env("capital-gateway")
    trading_env = env.read_env("trading-mcp")
    if gateway_env is None or trading_env is None:
        return []  # already reported as a missing file

    gateway_key = env_value(gateway_env, "GATEWAY_API_KEY")
    trading_key = env_value(trading_env, "CAPITAL_GATEWAY_API_KEY")

    if not trading_key:
        return [
            (
                "modules/trading-mcp/.env has no CAPITAL_GATEWAY_API_KEY — the gateway "
                "requires it from every caller, loopback included"
            )
        ]
    if gateway_key and gateway_key != trading_key:
        return [
            (
                "modules/trading-mcp/.env's CAPITAL_GATEWAY_API_KEY does not match "
                "modules/capital-gateway/.env's GATEWAY_API_KEY — trading-mcp would be "
                "refused by the gateway and exit before it listens"
            )
        ]
    return []


# --- the advisories, which are not refusals ------------------------------------------
#
# Each of these is a supported state, and each looks from the operator's seat like a broken
# module rather than a missing line. That is the whole reason they are said out loud.

ADVISORIES: tuple[tuple[str, str, str, str], ...] = (
    (
        "agent",
        "MARKET_MCP_URL",
        "the agent will run without tools",
        "8040",
    ),
    (
        "teams",
        "MARKET_MCP_URL",
        "teams whose agents assign tools will refuse to run rather than answer without them",
        "8040",
    ),
    (
        "teams",
        "TRADING_MCP_URL",
        "teams will have no order tools, and one assigning them refuses to run",
        "8060",
    ),
    (
        "agent",
        "TEAMS_MCP_URL",
        "the agent will have no tools for building or running teams",
        "8070",
    ),
    (
        "agent",
        "TRADING_MCP_URL",
        "the agent will not see positions and cannot send an order",
        "8060",
    ),
)


def advisories(env: Environment) -> list[str]:
    lines: list[str] = []
    for module, key, consequence, port in ADVISORIES:
        text = env.read_env(module)
        if text is None:
            continue
        if not env_value(text, key):
            lines.append(f"modules/{module}/.env has no {key} — {consequence}.")
            lines.append(f"  Add {key}=http://{LOOPBACK}:{port} as .env.example does.")
    return lines


# --- what to start, and in what order ------------------------------------------------


def services_to_start(*, start_terminal: bool) -> tuple[Service, ...]:
    if start_terminal:
        return SERVICES
    return tuple(service for service in SERVICES if service.name != "terminal")


# --- the console ---------------------------------------------------------------------


def _enable_ansi() -> bool:
    """Windows consoles need VT processing turned on; everything else already has it."""
    if not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
        return False
    if not WINDOWS:
        return True
    try:
        import ctypes

        handle = ctypes.windll.kernel32.GetStdHandle(-11)  # type: ignore[attr-defined]
        mode = ctypes.c_uint32()
        if not ctypes.windll.kernel32.GetConsoleMode(handle, ctypes.byref(mode)):  # type: ignore[attr-defined]
            return False
        return bool(
            ctypes.windll.kernel32.SetConsoleMode(handle, mode.value | 0x0004)  # type: ignore[attr-defined]
        )
    except (OSError, AttributeError):
        # A console that will not take VT processing gets plain text, not a crash.
        return False


COLOUR = _enable_ansi()


def paint(text: str, colour: str) -> str:
    return f"{colour}{text}{RESET}" if COLOUR else text


def say(message: str) -> None:
    print(paint(message, CYAN), flush=True)


def ok(message: str) -> None:
    print(paint(message, GREEN), flush=True)


def note(message: str) -> None:
    print(paint(message, DIM), flush=True)


def fail(message: str) -> None:
    print(paint(message, RED), file=sys.stderr, flush=True)


# --- running the processes -----------------------------------------------------------


@dataclass
class Running:
    service: Service
    process: subprocess.Popen[str]
    reader: threading.Thread = field(repr=False, default_factory=threading.Thread)


class Stack:
    """The processes this run started, and nothing else.

    Every one of them is killed on the way out, including its children: `uv run` spawns
    uvicorn and pnpm spawns vite, and it is the children that hold the ports. Killing the
    parent alone is what leaves something squatting on 8010 until the next reboot — the
    reason `dev.ps1` needed a port sweep at the end.
    """

    def __init__(self) -> None:
        self.running: list[Running] = []

    def start(self, service: Service, command: Sequence[str]) -> Running:
        creationflags = CREATE_NEW_PROCESS_GROUP if WINDOWS else 0
        process = subprocess.Popen(
            resolve_command(command),
            cwd=service.directory,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            start_new_session=not WINDOWS,
            creationflags=creationflags,
        )
        entry = Running(service=service, process=process)
        entry.reader = threading.Thread(
            target=self._pump, args=(service, process), daemon=True, name=f"log-{service.name}"
        )
        entry.reader.start()
        self.running.append(entry)
        return entry

    @staticmethod
    def _pump(service: Service, process: subprocess.Popen[str]) -> None:
        assert process.stdout is not None
        prefix = paint(f"[{service.log_prefix}]", service.colour)
        for line in process.stdout:
            print(f"{prefix} {line.rstrip()}", flush=True)

    def first_dead(self) -> Running | None:
        return next((entry for entry in self.running if entry.process.poll() is not None), None)

    def stop(self) -> None:
        for entry in reversed(self.running):
            _terminate_tree(entry.process)
        for entry in reversed(self.running):
            try:
                entry.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                entry.process.kill()


def resolve_command(command: Sequence[str]) -> list[str]:
    """Resolve the executable on PATH before handing it to `Popen`.

    On Windows `pnpm` and `npx` are `.CMD` shims, and CreateProcess only ever appends
    `.exe` — so `Popen(["pnpm", ...])` raises `FileNotFoundError [WinError 2]` while
    `shutil.which("pnpm")` happily finds `pnpm.CMD`. That split is what makes the failure
    nasty: `preflight` uses `which`, passes, and the run dies on the *last* service after
    all seven back ends are up, taking them down with it.

    `dev.sh` never met this (PATH lookup is the shell's) and `dev.ps1` never met it either
    (PowerShell resolves `.CMD`), so it is new with the port, not carried over.
    """
    if not command:
        return []
    resolved = shutil.which(command[0])
    return [resolved or command[0], *command[1:]]


def _terminate_tree(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    try:
        if WINDOWS:
            # `taskkill /T` is the only thing that reaches vite under pnpm under this
            # process; CTRL_BREAK reaches the group but not a grandchild that detached.
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                check=False,
            )
        else:
            # Guarded on WINDOWS above; pyright type-checks this file for win32 too.
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)  # type: ignore[attr-defined]
    except (OSError, subprocess.SubprocessError):
        process.terminate()


def wait_for_http(url: str, label: str, *, timeout: float = WAIT_SECONDS) -> bool:
    import httpx

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            response = httpx.get(url, timeout=2.0)
        except httpx.HTTPError:
            response = None
        if response is not None and response.status_code < 400:
            return True
        time.sleep(0.5)
    fail(f"{label} did not answer {url} within {int(timeout)}s.")
    note("Its output is above. A cold 'uv run' resolving dependencies is the usual slow part.")
    return False


# --- the database and the migrations -------------------------------------------------


def _compose(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", "compose", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def start_database() -> bool:
    """`--wait` blocks on compose.yaml's healthcheck, which names the user and the database
    on purpose: a bare `pg_isready` answers before first-boot initialisation finishes, and
    the migrations below would then race it."""
    say("Starting the database container...")
    if _compose("up", "-d", "--wait", "db").returncode != 0:
        fail(
            "the database container did not become healthy — 'docker compose logs db' has "
            "the reason."
        )
        return False
    ok("Database is up.")
    return True


def _psql(*args: str) -> subprocess.CompletedProcess[str]:
    return _compose(
        "exec",
        "-T",
        "db",
        "psql",
        "-U",
        "market_data",
        "-d",
        "market_data",
        "-v",
        "ON_ERROR_STOP=1",
        *args,
    )


def ensure_databases(names: Iterable[str] = LOGICAL_DATABASES) -> bool:
    say("Ensuring the agent and teams databases exist...")
    for name in names:
        role_exists = "1" in _psql(
            "-tAc", f"SELECT 1 FROM pg_roles WHERE rolname = '{name}'"
        ).stdout
        if not role_exists and _psql(
            "-c", f"CREATE ROLE {name} LOGIN PASSWORD 'change-me';"
        ).returncode != 0:
            fail(f"could not create the '{name}' role")
            return False

        database_exists = "1" in _psql(
            "-tAc", f"SELECT 1 FROM pg_database WHERE datname = '{name}'"
        ).stdout
        if not database_exists and _psql(
            "-c", f"CREATE DATABASE {name} OWNER {name};"
        ).returncode != 0:
            fail(f"could not create the '{name}' database")
            return False
    ok("agent and teams databases are ready.")
    return True


def apply_migrations(modules: Iterable[str] = MIGRATING_MODULES) -> bool:
    """Applied every run, not only on a fresh one: a checkout that has just pulled a new
    migration is exactly the case where forgetting this produces an error reading like a bug
    in the module."""
    say("Applying migrations...")
    for module in modules:
        done = subprocess.run(
            ["uv", "run", "alembic", "upgrade", "head"],
            cwd=MODULES / module,
            check=False,
        )
        if done.returncode != 0:
            fail(f"{module}'s migrations failed — it would fail on its first query, so stopping.")
            return False
    ok("Schema is up to date.")
    return True


# --- the command line ---------------------------------------------------------------


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Both spellings of the one flag.

    `-NoTerminal` is what `dev.ps1` documents and what the operator's fingers know, and
    `--no-terminal` is what `dev.sh` documents. Accepting both is what keeps the two
    wrappers from being the place a difference can appear again.
    """
    parser = argparse.ArgumentParser(
        prog="dev.py",
        description="Start the whole stack locally, in dependency order.",
    )
    parser.add_argument(
        "--no-terminal",
        "-NoTerminal",
        dest="start_terminal",
        action="store_false",
        help="back end only, e.g. to run the live tests",
    )
    parser.add_argument(
        "--explain",
        action="store_true",
        help="print the start order and the reason for each position, then exit",
    )
    return parser.parse_args(list(argv) if argv is not None else None)


def explain() -> None:
    print("Start order, and why each service is where it is:\n")
    for index, service in enumerate(SERVICES, start=1):
        print(f"{index}. {service.name} (port {service.port})")
        print(f"   {service.why}\n")


# --- the run ------------------------------------------------------------------------


def real_environment() -> Environment:
    def read_env(module: str) -> str | None:
        path = MODULES / module / ".env"
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            return None

    def port_in_use(port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(0.5)
            return probe.connect_ex((LOOPBACK, port)) == 0

    def port_owner(port: int) -> str:
        """Best-effort, for the message only. Often empty, and that is fine.

        Worth having anyway: "port 8010 is already in use by uvicorn (pid 4312)" names the
        leftover run, and "already in use" alone sends the reader looking for a second
        stack that is not there.
        """
        pid = _listening_pid(port)
        if pid is None:
            return ""
        return f" by {_process_name(pid) or 'a process'} (pid {pid})"

    def docker_daemon_answers() -> bool:
        return (
            subprocess.run(["docker", "info"], capture_output=True, check=False).returncode == 0
        )

    return Environment(
        which=lambda name: shutil.which(name),
        read_env=read_env,
        port_in_use=port_in_use,
        port_owner=port_owner,
        docker_daemon_answers=docker_daemon_answers,
        node_modules_present=lambda: (MODULES / "terminal" / "node_modules").is_dir(),
    )


def _listening_pid(port: int) -> int | None:
    """Who is listening on `port`, asked the way each platform will answer."""
    if WINDOWS:
        done = subprocess.run(
            ["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True, check=False
        )
        for line in done.stdout.splitlines():
            fields = line.split()
            listening = len(fields) >= 5 and fields[0] == "TCP" and fields[3] == "LISTENING"
            if listening and fields[1].rsplit(":", 1)[-1] == str(port):
                return int(fields[4])
        return None

    # `lsof` rather than `ss`: it is what macOS has, and a service left over from a previous
    # run does not always show up under the current user in the alternatives.
    done = subprocess.run(
        ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
        capture_output=True,
        text=True,
        check=False,
    )
    first = done.stdout.split()
    return int(first[0]) if first else None


def _process_name(pid: int) -> str | None:
    if WINDOWS:
        done = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH", "/FO", "CSV"],
            capture_output=True,
            text=True,
            check=False,
        )
        line = done.stdout.strip().splitlines()
        return line[0].split('","')[0].strip('"') if line else None

    done = subprocess.run(
        ["ps", "-p", str(pid), "-o", "comm="], capture_output=True, text=True, check=False
    )
    return done.stdout.strip() or None


def terminal_command(env: Environment) -> tuple[str, ...]:
    """pnpm is what the module documents, but a machine with only npm can still run a dev
    server, and refusing over the choice of package manager helps nobody."""
    terminal = next(service for service in SERVICES if service.name == "terminal")
    if env.which("pnpm"):
        return terminal.command
    return terminal.fallback_command


def ready_lines(*, start_terminal: bool) -> list[str]:
    lines = []
    if start_terminal:
        lines += [
            "  Terminal            http://localhost:5173",
            "  Instruments panel   http://localhost:5173/instruments",
        ]
    lines += [
        f"  market-data docs    http://{LOOPBACK}:8020/docs",
        f"  Gateway docs        http://{LOOPBACK}:8010/docs",
        f"  market-mcp health   http://{LOOPBACK}:8040/health",
        f"  trading-mcp health  http://{LOOPBACK}:8060/health",
        f"  teams-mcp health    http://{LOOPBACK}:8070/health",
        f"  agent docs          http://{LOOPBACK}:8030/docs",
        f"  teams docs          http://{LOOPBACK}:8050/docs",
        (
            "  Database            market_data, agent, teams @ localhost:55432 "
            "(compose.yaml; 'docker compose down' keeps the data)"
        ),
    ]
    return lines


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.explain:
        explain()
        return 0

    env = real_environment()
    problems = preflight(env, start_terminal=args.start_terminal)
    if problems:
        fail("Cannot start:")
        for problem in problems:
            fail(f"  - {problem}")
        return 1

    for line in advisories(env):
        note(line)

    if not start_database() or not ensure_databases() or not apply_migrations():
        return 1

    stack = Stack()
    try:
        for service in services_to_start(start_terminal=args.start_terminal):
            command = terminal_command(env) if service.name == "terminal" else service.command
            say(f"Starting {service.name} on port {service.port}...")
            stack.start(service, command)
            health = service.health_url
            if health is not None and not wait_for_http(health, service.name):
                return 1
            if health is not None:
                ok(f"{service.name} is answering.")

        print()
        ok("Ready:")
        for line in ready_lines(start_terminal=args.start_terminal):
            print(line)
        print()
        note("Nothing is archived until a pair is added in the Archive panel — deliberate.")
        note("Ctrl+C to stop the services.")
        print()

        while True:
            dead = stack.first_dead()
            if dead is not None:
                fail(f"{dead.service.name} exited ({dead.process.returncode}). Stopping the rest.")
                return 1
            time.sleep(1)
    except KeyboardInterrupt:
        print()
        say("Stopping...")
        return 0
    finally:
        stack.stop()


if __name__ == "__main__":
    sys.exit(main())
