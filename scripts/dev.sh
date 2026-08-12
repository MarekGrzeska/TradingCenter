#!/usr/bin/env bash
#
# Everything the terminal needs, in the order it needs it — the macOS and Linux
# counterpart of dev.ps1.
#
#   migrations  ->  capital-gateway  ->  market-data  ->  agent  ->  terminal
#
# The order is not tidiness. market-data opens a subscription per tracked pair the
# moment it starts, so a gateway that is not listening yet costs it a round of
# backoff; the terminal's charts read the archive, so starting it first fills the
# console with proxy errors that mean nothing; and the agent has nothing that depends
# on it, so it goes last among the back ends. Each step waits for the one before it to
# actually answer, not merely to have been launched.
#
# The database is the container in ../compose.yaml — started here, before migrations
# (openspec/changes/local-dev-database-in-docker; the spell in Azure is over, production
# stays there and development does not). `docker compose down` keeps the data.
#
# `agent`'s own database is a second logical database in that same container, created
# here if missing rather than through docker-entrypoint-initdb.d — that only runs on a
# volume's first boot, so it would never fire for anyone who already has
# tradingcenter-db-data from before this module existed (design.md, "Baza: druga baza
# logiczna, jeden serwer").
#
#   ./scripts/dev.sh              # everything
#   ./scripts/dev.sh --no-terminal    # back end only, e.g. to run the live tests
#
# Nothing depends on this script: every module still starts on its own with the
# command in its README.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GATEWAY_DIR="$REPO_ROOT/modules/capital-gateway"
ARCHIVE_DIR="$REPO_ROOT/modules/market-data"
AGENT_DIR="$REPO_ROOT/modules/agent"
TERMINAL_DIR="$REPO_ROOT/modules/terminal"

GATEWAY_PORT=8010
ARCHIVE_PORT=8020
AGENT_PORT=8030
TERMINAL_PORT=5173

# 127.0.0.1 rather than "localhost": uvicorn binds IPv4 loopback, and on a machine
# where "localhost" resolves to ::1 first the wait below would never succeed.
GATEWAY_URL="http://127.0.0.1:$GATEWAY_PORT"
ARCHIVE_URL="http://127.0.0.1:$ARCHIVE_PORT"
AGENT_URL="http://127.0.0.1:$AGENT_PORT"

START_TERMINAL=1
WAIT_SECONDS=120

for arg in "$@"; do
  case "$arg" in
    --no-terminal) START_TERMINAL=0 ;;
    -h|--help) sed -n '2,29p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $arg (try --help)" >&2; exit 2 ;;
  esac
done

BLUE=$'\033[34m'; MAGENTA=$'\033[35m'; CYAN=$'\033[36m'; YELLOW=$'\033[33m'
GREEN=$'\033[32m'; RED=$'\033[31m'; DIM=$'\033[2m'; RESET=$'\033[0m'

say()  { printf '%s%s%s\n' "$CYAN" "$1" "$RESET"; }
ok()   { printf '%s%s%s\n' "$GREEN" "$1" "$RESET"; }
fail() { printf '%s%s%s\n' "$RED" "$1" "$RESET" >&2; }
note() { printf '%s%s%s\n' "$DIM" "$1" "$RESET"; }

# --- what has to be true before anything starts -------------------------------
#
# Checked up front and reported together. Finding out about a missing .env after
# two services are already running means killing them to fix one line.

problems=()

command -v uv >/dev/null 2>&1 || problems+=("uv is not on PATH (runs both Python services) — https://docs.astral.sh/uv/")

# The database lives in a container again, so Docker is back to being a requirement for
# running the stack, not only for testing market-data.
if ! command -v docker >/dev/null 2>&1; then
  problems+=("docker is not on PATH (runs the database, compose.yaml) — https://docs.docker.com/get-docker/")
elif ! docker info >/dev/null 2>&1; then
  problems+=("docker is installed but the daemon is not answering — start Docker Desktop (or the service)")
fi

[[ -f "$GATEWAY_DIR/.env" ]] || problems+=("$GATEWAY_DIR/.env is missing — copy .env.example and fill in demo credentials")
[[ -f "$ARCHIVE_DIR/.env" ]] || problems+=("$ARCHIVE_DIR/.env is missing — copy .env.example; the defaults match compose.yaml")
[[ -f "$AGENT_DIR/.env" ]] || problems+=("$AGENT_DIR/.env is missing — copy .env.example and fill in OPENAI_API_KEY")

if (( START_TERMINAL )); then
  if command -v pnpm >/dev/null 2>&1; then
    TERMINAL_RUN=(pnpm exec vite --port "$TERMINAL_PORT" --strictPort)
    TERMINAL_INSTALL="pnpm install"
  elif command -v npm >/dev/null 2>&1; then
    # pnpm is what the module documents, but a machine with only npm can still
    # run a dev server, and refusing over the choice of package manager helps
    # nobody.
    TERMINAL_RUN=(npx vite --port "$TERMINAL_PORT" --strictPort)
    TERMINAL_INSTALL="npm install"
  else
    problems+=("neither pnpm nor npm is on PATH (runs the terminal) — https://pnpm.io/installation")
  fi
  [[ -d "$TERMINAL_DIR/node_modules" ]] || problems+=("$TERMINAL_DIR/node_modules is missing — run '${TERMINAL_INSTALL:-pnpm install}' in modules/terminal")
fi

# A port already taken is the commonest reason a run appears to hang: the new
# process cannot bind, and the wait then watches somebody else's service.
#
# Tested by connecting rather than by asking lsof who owns it. A service left over
# from a previous run does not always show up under the current user's `lsof`.
port_in_use() {
  (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null && exec 3<&- && return 0
  return 1
}

# Best-effort, for the message only: often empty, and that is fine.
port_owner() {
  local pid
  pid="$(lsof -nP -iTCP:"$1" -sTCP:LISTEN -t 2>/dev/null | head -1 || true)"
  [[ -z "$pid" ]] && return 1
  printf ' by %s (pid %s)' "$(ps -p "$pid" -o comm= 2>/dev/null || echo process)" "$pid"
}

ports=("$GATEWAY_PORT" "$ARCHIVE_PORT" "$AGENT_PORT")
(( START_TERMINAL )) && ports+=("$TERMINAL_PORT")
for port in "${ports[@]}"; do
  port_in_use "$port" || continue
  owner="$(port_owner "$port" || true)"
  problems+=("port $port is already in use${owner} — stop it, or it is a leftover run")
done

# The quiet disaster this guards against: `.env` still pointing at the Azure server —
# production, or the retired dev database — instead of the local container. config.py
# refuses the same thing at startup (no DATABASE_USER means loopback only); repeating
# the check here just refuses earlier, before anything has been launched, with the file
# to fix named. Reads the host between the optional `user:pass@` and the port/path.
archive_db_host="$(sed -n 's|^DATABASE_URL=[a-z+]*://\([^@/]*@\)\{0,1\}\([^:/?]*\).*|\2|p' "$ARCHIVE_DIR/.env" 2>/dev/null | head -1)"
case "$archive_db_host" in
  ""|localhost|127.*|::1) ;;
  *) problems+=("modules/market-data/.env's DATABASE_URL points at '$archive_db_host' — local runs use the compose.yaml container (localhost), never a remote database") ;;
esac

agent_db_host="$(sed -n 's|^DATABASE_URL=[a-z+]*://\([^@/]*@\)\{0,1\}\([^:/?]*\).*|\2|p' "$AGENT_DIR/.env" 2>/dev/null | head -1)"
case "$agent_db_host" in
  ""|localhost|127.*|::1) ;;
  *) problems+=("modules/agent/.env's DATABASE_URL points at '$agent_db_host' — local runs use the compose.yaml container (localhost), never a remote database") ;;
esac

if (( ${#problems[@]} )); then
  fail "Cannot start:"
  for problem in "${problems[@]}"; do fail "  - $problem"; done
  exit 1
fi

# --- shutting everything down -------------------------------------------------

# Two lists. `SERVICE_PIDS` is what has to stay alive; `ALL_PIDS` adds the log
# printers, which are cleaned up but whose death means nothing.
SERVICE_PIDS=()
ALL_PIDS=()
LOG_DIR="$(mktemp -d)"

cleanup() {
  local status=$?
  trap - EXIT INT TERM
  echo
  say "Stopping..."
  for pid in "${ALL_PIDS[@]:-}"; do
    [[ -n "${pid:-}" ]] || continue
    # The whole group: `uv run` spawns uvicorn and vite spawns esbuild, and it is
    # the children that hold the ports. Killing the parent alone is what leaves
    # something squatting on 8010 until the next reboot.
    kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
  rm -rf "$LOG_DIR"
  exit "$status"
}
trap cleanup EXIT INT TERM

# Each service gets a prefix so one console can carry three of them.
#
# The prefixing is a read loop rather than `sed -u`: `-u` is a GNU extension and
# the sed macOS ships is BSD's, so a machine without GNU sed on PATH would lose
# every service's output — silently, since the pipeline still runs.
run_service() {
  local label="$1" colour="$2" dir="$3"; shift 3
  ( cd "$dir" && exec "$@" ) > "$LOG_DIR/$label.out" 2>&1 &
  local pid=$!
  SERVICE_PIDS+=("$pid")
  ALL_PIDS+=("$pid")
  (
    tail -n +1 -f "$LOG_DIR/$label.out" 2>/dev/null | while IFS= read -r line; do
      printf '%s[%s]%s %s\n' "$colour" "$label" "$RESET" "$line"
    done
  ) &
  ALL_PIDS+=("$!")
}

wait_for_http() {
  local url="$1" label="$2" deadline=$((SECONDS + WAIT_SECONDS))
  while (( SECONDS < deadline )); do
    if curl -fsS --max-time 2 "$url" >/dev/null 2>&1; then return 0; fi
    sleep 0.5
  done
  fail "$label did not answer $url within ${WAIT_SECONDS}s."
  note "Its output is above. A cold 'uv run' resolving dependencies is the usual slow part."
  return 1
}

# --- the database ---------------------------------------------------------------
#
# `--wait` blocks on the healthcheck in compose.yaml, which names the user and the
# database on purpose: a bare `pg_isready` answers before first-boot initialisation
# finishes, and the migrations below would then race it.

say "Starting the database container..."
if ! ( cd "$REPO_ROOT" && docker compose up -d --wait db ); then
  fail "the database container did not become healthy — 'docker compose logs db' has the reason."
  exit 1
fi
ok "Database is up."

# --- the agent's own database ----------------------------------------------------
#
# A second logical database in the same container, not a second container — the free
# grant is one Postgres server and this mirrors it (design.md, "Baza: druga baza
# logiczna, jeden serwer"). Checked and created here rather than through
# docker-entrypoint-initdb.d, which only ever runs against an empty volume: anyone with
# a tradingcenter-db-data from before this module existed would never see it fire.
psql_super() { ( cd "$REPO_ROOT" && docker compose exec -T db psql -U market_data -d market_data -v ON_ERROR_STOP=1 "$@" ); }

say "Ensuring the agent database exists..."
if ! psql_super -tAc "SELECT 1 FROM pg_roles WHERE rolname = 'agent'" | grep -q 1; then
  psql_super -c "CREATE ROLE agent LOGIN PASSWORD 'change-me';" || { fail "could not create the 'agent' role"; exit 1; }
fi
if ! psql_super -tAc "SELECT 1 FROM pg_database WHERE datname = 'agent'" | grep -q 1; then
  psql_super -c "CREATE DATABASE agent OWNER agent;" || { fail "could not create the 'agent' database"; exit 1; }
fi
ok "agent database is ready."

# --- migrations -----------------------------------------------------------------

# Applied every run, not only on a fresh one: a checkout that has just pulled a
# new migration is exactly the case where forgetting this produces an error that
# reads like a bug in the archive.
say "Applying migrations..."
if ! ( cd "$ARCHIVE_DIR" && uv run alembic upgrade head ); then
  fail "migrations failed — the archive would fail on its first query, so stopping here."
  exit 1
fi
if ! ( cd "$AGENT_DIR" && uv run alembic upgrade head ); then
  fail "agent's migrations failed — it would fail on its first query, so stopping here."
  exit 1
fi
ok "Schema is up to date."

# --- capital-gateway ----------------------------------------------------------

say "Starting capital-gateway on port $GATEWAY_PORT..."
run_service "gateway " "$BLUE" "$GATEWAY_DIR" uv run uvicorn capital_gateway.app:app --reload --port "$GATEWAY_PORT"
# "/" specifically — every other route needs X-Gateway-Key since group 1's auth work,
# and "/" is the one exception carved out for exactly this kind of health probe.
wait_for_http "$GATEWAY_URL/" "capital-gateway" || exit 1
ok "capital-gateway is answering."

# --- market-data --------------------------------------------------------------
#
# After the gateway, because it subscribes to it as it starts. Before the
# terminal, because the terminal's charts read it.

say "Starting market-data on port $ARCHIVE_PORT..."
run_service "archive " "$MAGENTA" "$ARCHIVE_DIR" uv run uvicorn market_data.app:app --reload --port "$ARCHIVE_PORT"
wait_for_http "$ARCHIVE_URL/health" "market-data" || exit 1
ok "market-data is answering."

# --- agent ----------------------------------------------------------------------
#
# Last among the back ends: nothing else calls it, so nothing else waits on it —
# unlike the gateway, which market-data subscribes to as it starts.

say "Starting agent on port $AGENT_PORT..."
run_service "agent   " "$YELLOW" "$AGENT_DIR" uv run uvicorn agent.app:app --reload --port "$AGENT_PORT"
wait_for_http "$AGENT_URL/health" "agent" || exit 1
ok "agent is answering."

# --- the terminal -------------------------------------------------------------

if (( START_TERMINAL )); then
  say "Starting the terminal on port $TERMINAL_PORT..."
  run_service "terminal" "$CYAN" "$TERMINAL_DIR" "${TERMINAL_RUN[@]}"
fi

echo
ok "Ready:"
if (( START_TERMINAL )); then
  echo "  Terminal            http://localhost:$TERMINAL_PORT"
  echo "  Instruments panel   http://localhost:$TERMINAL_PORT/instruments"
fi
echo "  market-data docs    $ARCHIVE_URL/docs"
echo "  Gateway docs        $GATEWAY_URL/docs"
echo "  agent docs          $AGENT_URL/docs"
echo "  Database            market_data @ localhost:55432 (compose.yaml; 'docker compose down' keeps the data)"
echo
note "Nothing is archived until a pair is added in the Archive panel — that is deliberate."
note "Ctrl+C to stop the services."
echo

# Polled rather than `wait -n`, which macOS cannot do: it ships bash 3.2, where
# `wait -n` is not an option at all — it fails instantly, and the script then
# announces a dead service while all of them are running perfectly. Everything
# else here is written to the same 3.2 floor.
while :; do
  for pid in "${SERVICE_PIDS[@]}"; do
    if ! kill -0 "$pid" 2>/dev/null; then
      fail "A service exited. Stopping the rest."
      exit 1
    fi
  done
  sleep 1
done
