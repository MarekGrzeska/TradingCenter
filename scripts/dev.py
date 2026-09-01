"""Everything the terminal needs, in the order it needs it — on every platform, once. This replaces `dev.sh`
and `dev.ps1`, which were one script written twice and drifted three times, each in one of them only.

    uv run python scripts/dev.py --no-terminal   # back end only, e.g. to run the live tests
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
# below into a replacement character. Reconfigured here rather than by asking for PYTHONUTF8.
for _stream in (sys.stdout, sys.stderr):
    if isinstance(_stream, io.TextIOWrapper):
        _stream.reconfigure(encoding="utf-8", errors="replace")
# Absent off Windows, so read once rather than referenced inside a branch pyright still
# checks for the other platform.
CREATE_NEW_PROCESS_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)


# One row per service, in start order. `why` used to be a comment beside a hand-written start
# block in two files; it stays with the row so moving the row moves the reason.


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
    # Only a front end has one, for a machine with npm and no pnpm.
    fallback_command: tuple[str, ...] = ()
    # Not waited for, dropped by `--no-terminal`, and started through whichever package manager is
    # there. A property because two services answer to it now, and a name is not a kind.
    front_end: bool = False

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
# Bright green went to trading-mcp, the one tool server that is still a process of its own.
BRIGHT_GREEN = "\033[92m"
# And bright blue to the strategy platform. Two services sharing a colour is the one thing
# this field exists to prevent — the logs interleave, and colour is how a reader tells them apart.
BRIGHT_BLUE = "\033[94m"
# And bright magenta to the phone screen, whose log interleaves with the terminal's cyan.
BRIGHT_MAGENTA = "\033[95m"
# And bright cyan to the post archive: every other colour here is taken, and two services sharing
# one is the thing this field exists to prevent.
BRIGHT_CYAN = "\033[96m"
# And bright yellow to the door to Telegram. Red is the failure colour and dim is the quiet one,
# so this is the last ordinary colour left — a tenth back end would need a scheme, not a constant.
BRIGHT_YELLOW = "\033[93m"

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
            "starts, so a gateway not listening yet costs it a round of backoff. It also "
            "serves the tool surface at /mcp, which is why nothing here starts a separate "
            "one any more."
        ),
    ),
    Service(
        name="trading-mcp",
        module="trading-mcp",
        port=8060,
        # No `--reload`: this one is not started through uvicorn's CLI, so a code
        # change here needs a manual restart.
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
        name="polymarket-data",
        module="polymarket-data",
        port=8070,
        command=(
            "uv", "run", "uvicorn", "polymarket_data.app:app", "--reload", "--port", "8070"
        ),
        log_prefix="polymkt ",
        colour=GREEN,
        health_path="/health",
        why=(
            "Independent of the gateway — its upstream is Polymarket, not capital.com, so "
            "nothing above it has to be running. Before the workbench for the same reason "
            "market-data is: the workbench reads its tool list on the first turn that "
            "wants one, and a server still coming up means a turn answered without those "
            "tools rather than an error anyone would notice."
        ),
    ),
    Service(
        name="social-data",
        module="social-data",
        port=8090,
        command=("uv", "run", "uvicorn", "social_data.app:app", "--reload", "--port", "8090"),
        log_prefix="social  ",
        colour=BRIGHT_CYAN,
        health_path="/health",
        why=(
            "Independent of everything above it — its upstream is a public feed, and it "
            "collects on its own loop whether or not anybody asks. Before the workbench "
            "for the reason polymarket-data is: the tool list is read on the first turn "
            "that wants one, and a server still coming up means a turn answered without "
            "those tools rather than an error anyone would notice."
        ),
    ),
    Service(
        name="strategy",
        module="strategy",
        port=8080,
        command=("uv", "run", "uvicorn", "strategy.app:app", "--reload", "--port", "8080"),
        log_prefix="strategy",
        colour=BRIGHT_BLUE,
        health_path="/health",
        why=(
            "After market-data, whose REST contract is the only thing it reads — but not "
            "waiting on it the way trading-mcp waits on the gateway: this one starts "
            "without reaching its upstream at all, and an archive still coming up costs "
            "it one evaluation that records why it could not see. Before the workbench, "
            "because a trigger there reads pending_setups here."
        ),
    ),
    Service(
        name="telegram-gateway",
        module="telegram-gateway",
        port=8100,
        command=(
            "uv", "run", "uvicorn", "telegram_gateway.app:app", "--reload", "--port", "8100"
        ),
        log_prefix="telegram",
        colour=BRIGHT_YELLOW,
        health_path="/health",
        why=(
            "Independent of everything above it — its upstream is Telegram, and it sends "
            "only when somebody asks. Before the workbench for the reason every tool server "
            "is: the tool list is read on the first turn that wants one. Its other two "
            "callers, social-data and strategy, do not wait on it at all — without a "
            "gateway to reach they collect and decide as usual, and simply say nothing."
        ),
    ),
    Service(
        name="workbench",
        module="workbench",
        port=8030,
        command=("uv", "run", "uvicorn", "workbench.app:app", "--reload", "--port", "8030"),
        log_prefix="workbnch",
        colour=YELLOW,
        health_path="/health",
        why=(
            "Last among the back ends: nothing else calls it, so nothing waits on it. The "
            "conversation and the teams catalogue are one process here — 8050 has belonged "
            "to nobody since `agent-and-teams-one-workbench`, and 8070 stopped being "
            "nobody's when polymarket-data claimed it. It calls four tool servers now, "
            "and each tool list is read on the first turn that wants one, so a server "
            "still coming up means a turn answered without those tools rather than an "
            "error anyone would notice."
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
            "After the back ends, because its charts read the archive — starting it first "
            "fills the console with proxy errors that mean nothing."
        ),
        front_end=True,
    ),
    Service(
        name="pocket",
        module="pocket",
        port=5174,
        command=("pnpm", "exec", "vite", "--port", "5174", "--strictPort"),
        fallback_command=("npx", "vite", "--port", "5174", "--strictPort"),
        log_prefix="pocket  ",
        colour=BRIGHT_MAGENTA,
        health_path=None,
        why=(
            "After the terminal and for its reason, with one upstream rather than four: it "
            "reads polymarket-data and nothing else. Bound to loopback like everything else "
            "here — a phone on the same Wi-Fi needs `pnpm dev --host` in the module, which "
            "publishes the dev server to the network and is nobody's default."
        ),
        front_end=True,
    ),
)

# Every migration chain and which module owns it; `workbench` appears twice because it owns two databases.
# Redundant with each module's startup migration, and kept because it fails readably rather than under a lock.
MIGRATION_CHAINS: tuple[tuple[str, str | None], ...] = (
    ("market-data", None),
    ("workbench", "alembic-agent.ini"),
    ("workbench", "alembic-teams.ini"),
    ("polymarket-data", None),
    ("social-data", None),
    ("strategy", None),
    ("telegram-gateway", None),
)

# Created here if missing rather than through docker-entrypoint-initdb.d, which only runs against
# an empty volume and would never fire for a container from before these modules existed.
LOGICAL_DATABASES = ("agent", "teams", "polymarket", "social", "strategy", "telegram")



def env_value(text: str, key: str) -> str | None:
    """The first `KEY=value` in an `.env`, or None. Not a parser — a reader for four keys."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(f"{key}="):
            return stripped[len(key) + 1 :].strip()
    return None


def database_host(text: str, *, key: str = "DATABASE_URL") -> str | None:
    """The host out of a database URL, between the optional `user:pass@` and the port. The key is an
    argument because the workbench owns two databases and names them separately."""
    url = env_value(text, key)
    if not url:
        return None
    match = re.match(r"^[a-z+]*://(?:[^@/]*@)?([^:/?]*)", url)
    return match.group(1) if match else None


def is_loopback(host: str | None) -> bool:
    return not host or host == "localhost" or host.startswith("127.") or host == "::1"


# Collected and reported together. Finding out about a missing `.env` after two services
# are running means killing them to fix one line.

# Which `.env` each module needs, and what is missing from it if it is absent.
REQUIRED_ENV: tuple[tuple[str, str], ...] = (
    ("capital-gateway", "copy .env.example and fill in demo credentials"),
    ("market-data", "copy .env.example; the defaults match compose.yaml"),
# Two OpenAI keys, deliberately — the conversation's and the teams experiments', so the bill
# splits. `workbench/config.py` refuses to build Settings without either.
    (
        "workbench",
        "copy .env.example and fill in AGENT_OPENAI_API_KEY and TEAMS_OPENAI_API_KEY",
    ),
    # trading-mcp cannot fall back the way teams-mcp does: `config.py` requires the
    # gateway's caller key, and the gateway checks it on loopback too.
    (
        "trading-mcp",
        "copy .env.example and set CAPITAL_GATEWAY_API_KEY to the gateway's own GATEWAY_API_KEY",
    ),
    # Nothing to fill in: Polymarket's two surfaces are public, so this module is the one
    # here whose example file is already a working configuration.
    ("polymarket-data", "copy .env.example; the defaults match compose.yaml and need no key"),
    # A key is optional here and its absence is a supported state: without OPENAI_API_KEY the module
    # collects posts and leaves every reading empty, which /state says out loud.
    ("social-data", "copy .env.example; the defaults match compose.yaml, and the model key is optional"),
    ("strategy", "copy .env.example; the defaults match compose.yaml"),
    # The three account-session lines are meant to stay empty: without them the module sends and
    # refuses to create bots, which is a configuration it supports rather than a missing step.
    (
        "telegram-gateway",
        "copy .env.example; the defaults match compose.yaml, and the account session is optional",
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
    node_modules_present: Callable[[str], bool] = lambda _: True


def preflight(env: Environment, *, start_front_ends: bool) -> list[str]:
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

    if start_front_ends:
        if not env.which("pnpm") and not env.which("npm"):
            problems.append(
                "neither pnpm nor npm is on PATH (runs the terminal and pocket) — "
                "https://pnpm.io/installation"
            )
        installer = "pnpm install" if env.which("pnpm") or not env.which("npm") else "npm install"
        # Once per front end, not once for the pair: two modules keep their own dependencies, and
        # "node_modules is missing" without a name sends the operator to the wrong directory.
        for service in SERVICES:
            if service.front_end and not env.node_modules_present(service.module):
                problems.append(
                    f"modules/{service.module}/node_modules is missing — run "
                    f"'{installer}' in modules/{service.module}"
                )

    problems += _port_problems(env, start_front_ends=start_front_ends)
    problems += _database_host_problems(env)
    problems += _gateway_key_problems(env)
    return problems


def _port_problems(env: Environment, *, start_front_ends: bool) -> list[str]:
    """A taken port is the commonest reason a run appears to hang: the new process cannot bind and the
    wait watches somebody else's service. Tested by connecting — a leftover may run as another user."""
    problems: list[str] = []
    for service in services_to_start(start_front_ends=start_front_ends):
        if env.port_in_use(service.port):
            owner = env.port_owner(service.port)
            problems.append(
                f"port {service.port} is already in use{owner} — stop it, or it is a "
                f"leftover run ({service.name})"
            )
    return problems


def _database_host_problems(env: Environment) -> list[str]:
    """The quiet disaster: an `.env` still pointing at the Azure server. `config.py` refuses the same at
    startup; refusing here is earlier, before anything has been launched, and names the file to fix."""
    problems: list[str] = []
    for module, key in (
        ("market-data", "DATABASE_URL"),
        ("workbench", "AGENT_DATABASE_URL"),
        ("workbench", "TEAMS_DATABASE_URL"),
    ):
        text = env.read_env(module)
        if text is None:
            continue
        host = database_host(text, key=key)
        if not is_loopback(host):
            problems.append(
                f"modules/{module}/.env's {key} points at '{host}' — local runs use the "
                "compose.yaml container (localhost), never a remote database"
            )
    return problems


def _gateway_key_problems(env: Environment) -> list[str]:
    """The two halves of one credential, in two files. trading-mcp asks the gateway about the account
    before it opens a port, so a mismatch is not a failed tool call later but a run that dies at start."""
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


# Each of these is a supported state, and each looks from the operator's seat like a broken
# module rather than a missing line. That is the whole reason they are said out loud.

ADVISORIES: tuple[tuple[str, str, str, str], ...] = (
# 8020, not 8040: the archive serves its own tools at /mcp since `market-mcp-into-market-data`,
# and a .env copied before that change points at a port nothing listens on.
    (
        "workbench",
        "MARKET_MCP_URL",
        (
            "the agent will run without tools, and a team whose agents assign them will "
            "refuse to run rather than answer without them"
        ),
        "8020",
    ),
    (
        "workbench",
        "TRADING_MCP_URL",
        (
            "the agent will not see positions and cannot send an order, and a team "
            "assigning order tools refuses to run"
        ),
        "8060",
    ),
    (
        "workbench",
        "POLYMARKET_MCP_URL",
        (
            "the agent cannot say what a prediction market prices an event at, and a "
            "team assigning those tools refuses to run"
        ),
        "8070",
    ),
    (
        "workbench",
        "SOCIAL_MCP_URL",
        (
            "the agent cannot say what was posted, and a team assigning those tools "
            "refuses to run"
        ),
        "8090",
    ),
    (
        "workbench",
        "TELEGRAM_MCP_URL",
        (
            "the agent cannot send a notification, and a team assigning those tools "
            "refuses to run"
        ),
        "8100",
    ),
)

# Settings that stopped existing, and what a `.env` still carrying them is a sign of. Said rather
# than ignored, for the reason the advisories above exist: a line read by nothing looks like one that works.
RETIRED_SETTINGS: tuple[tuple[str, str], ...] = (
    (
        "TEAMS_MCP_URL",
        (
            "the team tools are a layer in the workbench now, reached without a port — "
            "this line is read by nothing"
        ),
    ),
    (
        "DATABASE_URL",
        "the workbench owns two databases: AGENT_DATABASE_URL and TEAMS_DATABASE_URL",
    ),
    (
        "OPENAI_API_KEY",
        "the two surfaces keep separate keys: AGENT_OPENAI_API_KEY and TEAMS_OPENAI_API_KEY",
    ),
    (
        "MODELS",
        "the two surfaces keep separate catalogues: AGENT_MODELS and TEAMS_MODELS",
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

    text = env.read_env("workbench")
    if text is not None:
        for key, why in RETIRED_SETTINGS:
            if env_value(text, key):
                lines.append(f"modules/workbench/.env still has {key} — {why}.")
    return lines



def services_to_start(*, start_front_ends: bool) -> tuple[Service, ...]:
    """`--no-terminal` keeps its name and drops both screens: neither is a back end, and a run with
    one of the two and not the other is not a state anybody asked for."""
    if start_front_ends:
        return SERVICES
    return tuple(service for service in SERVICES if not service.front_end)



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



@dataclass
class Running:
    service: Service
    process: subprocess.Popen[str]
    reader: threading.Thread = field(repr=False, default_factory=threading.Thread)


class Stack:
    """The processes this run started, and nothing else — each killed with its children, since `uv run`
    spawns uvicorn and pnpm spawns vite, and it is the children that hold the ports."""

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
    """On Windows `pnpm` is a `.CMD` shim and CreateProcess only appends `.exe`, so `Popen` raises
    WinError 2 where `shutil.which` succeeds — which is why preflight passes and the last service dies."""
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



def _compose(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", "compose", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def start_database() -> bool:
    """`--wait` blocks on compose.yaml's healthcheck, which names the user and the database on purpose:
    a bare `pg_isready` answers before first-boot initialisation finishes, and the migrations race it."""
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
    # Named rather than counted, and materialised first: a message naming two while creating three is
    # how the third goes unnoticed, and a generator would be spent by the join below.
    names = tuple(names)
    listed = ", ".join(names)
    say(f"Ensuring the {listed} databases exist...")
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
    ok(f"{listed} databases are ready.")
    return True


def apply_migrations(chains: Iterable[tuple[str, str | None]] = MIGRATION_CHAINS) -> bool:
    """Applied every run, not only on a fresh one: a checkout that has just pulled a migration is exactly
    where forgetting this produces an error reading like a bug in the module."""
    say("Applying migrations...")
    for module, config in chains:
        command = ["uv", "run", "alembic"]
        if config is not None:
            command += ["-c", config]
        command += ["upgrade", "head"]
        done = subprocess.run(command, cwd=MODULES / module, check=False)
        if done.returncode != 0:
            named = f"{module} ({config})" if config else module
            fail(f"{named}'s migrations failed — it would fail on its first query, so stopping.")
            return False
    ok("Schema is up to date.")
    return True



def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Both spellings of the one flag — `-NoTerminal` is what `dev.ps1` documents and `--no-terminal` what
    `dev.sh` does. Accepting both keeps the two wrappers from differing again."""
    parser = argparse.ArgumentParser(
        prog="dev.py",
        description="Start the whole stack locally, in dependency order.",
    )
    parser.add_argument(
        "--no-terminal",
        "-NoTerminal",
        dest="start_front_ends",
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
        """Best-effort, for the message only, and often empty. "port 8010 is already in use by uvicorn
        (pid 4312)" names the leftover run; "already in use" sends the reader looking for a second stack."""
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
        node_modules_present=lambda module: (MODULES / module / "node_modules").is_dir(),
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


def command_for(service: Service, env: Environment) -> tuple[str, ...]:
    """pnpm is what the modules document, but a machine with only npm can still run a dev server,
    and refusing over the choice of package manager helps nobody. Asked of every service rather
    than of the front ends alone: a back end has no fallback, so its answer is its own command."""
    if service.fallback_command and not env.which("pnpm"):
        return service.fallback_command
    return service.command


def ready_lines(*, start_front_ends: bool) -> list[str]:
    lines = []
    if start_front_ends:
        lines += [
            "  Terminal            http://localhost:5173",
            "  Instruments panel   http://localhost:5173/instruments",
            "  Pocket (phone)      http://localhost:5174",
        ]
    lines += [
        f"  market-data docs    http://{LOOPBACK}:8020/docs",
        f"  Gateway docs        http://{LOOPBACK}:8010/docs",
        f"  Archive tools       http://{LOOPBACK}:8020/mcp",
        f"  trading-mcp health  http://{LOOPBACK}:8060/health",
        f"  Workbench docs      http://{LOOPBACK}:8030/docs",
        f"  Polymarket docs     http://{LOOPBACK}:8070/docs",
        (
            "  Database            market_data, agent, teams, polymarket, social, strategy, "
            "telegram @ localhost:55432 "
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
    problems = preflight(env, start_front_ends=args.start_front_ends)
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
        for service in services_to_start(start_front_ends=args.start_front_ends):
            say(f"Starting {service.name} on port {service.port}...")
            stack.start(service, command_for(service, env))
            health = service.health_url
            if health is not None and not wait_for_http(health, service.name):
                return 1
            if health is not None:
                ok(f"{service.name} is answering.")

        print()
        ok("Ready:")
        for line in ready_lines(start_front_ends=args.start_front_ends):
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
