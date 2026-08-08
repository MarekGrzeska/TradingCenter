#!/usr/bin/env bash
#
# Everything the terminal needs, in the order it needs it — the macOS and Linux
# counterpart of dev.ps1.
#
#   database (container)  ->  migrations  ->  capital-gateway  ->  market-data  ->  terminal
#
# The order is not tidiness. market-data opens a subscription per tracked pair the
# moment it starts, so a gateway that is not listening yet costs it a round of
# backoff; and the terminal's charts read the archive, so starting it first fills
# the console with proxy errors that mean nothing. Each step waits for the one
# before it to actually answer, not merely to have been launched.
#
# Only PostgreSQL runs in a container. The services run here, where they reload on
# save and can be attached to.
#
#   ./scripts/dev.sh              # everything
#   ./scripts/dev.sh --no-terminal    # back end only, e.g. to run the live tests
#   ./scripts/dev.sh --fresh      # drop the database first and start empty
#
# Nothing depends on this script: every module still starts on its own with the
# command in its README.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GATEWAY_DIR="$REPO_ROOT/modules/capital-gateway"
ARCHIVE_DIR="$REPO_ROOT/modules/market-data"
TERMINAL_DIR="$REPO_ROOT/modules/terminal"

GATEWAY_PORT=8010
ARCHIVE_PORT=8020
TERMINAL_PORT=5173
# Matches compose.yaml's default. Both read DB_PORT, so overriding it here and
# there at once keeps them pointing at the same database.
DB_PORT="${DB_PORT:-55432}"

# 127.0.0.1 rather than "localhost": uvicorn binds IPv4 loopback, and on a machine
# where "localhost" resolves to ::1 first the wait below would never succeed.
GATEWAY_URL="http://127.0.0.1:$GATEWAY_PORT"
ARCHIVE_URL="http://127.0.0.1:$ARCHIVE_PORT"

START_TERMINAL=1
FRESH=0
WAIT_SECONDS=120

for arg in "$@"; do
  case "$arg" in
    --no-terminal) START_TERMINAL=0 ;;
    --fresh) FRESH=1 ;;
    -h|--help) sed -n '2,30p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $arg (try --help)" >&2; exit 2 ;;
  esac
done

BLUE=$'\033[34m'; MAGENTA=$'\033[35m'; CYAN=$'\033[36m'
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
command -v docker >/dev/null 2>&1 || problems+=("docker is not on PATH (runs PostgreSQL) — https://docs.docker.com/get-docker/")

if command -v docker >/dev/null 2>&1 && ! docker compose version >/dev/null 2>&1; then
  problems+=("this docker has no 'compose' subcommand — install Docker Compose v2")
fi

[[ -f "$GATEWAY_DIR/.env" ]] || problems+=("$GATEWAY_DIR/.env is missing — copy .env.example and fill in demo credentials")
[[ -f "$ARCHIVE_DIR/.env" ]] || problems+=("$ARCHIVE_DIR/.env is missing — copy .env.example (its defaults match compose.yaml)")

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
# Tested by connecting rather than by asking lsof who owns it. A PostgreSQL the
# machine installed for itself runs as another user, and `lsof` run as you does
# not list it at all — which is how the standard port looks free right up until
# Docker refuses to bind it.
port_in_use() {
  (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null && exec 3<&- && return 0
  return 1
}

# Whether the container this repository starts is itself what holds a port.
#
# Ctrl+C leaves the database running on purpose, so on the second run of the day
# its port is legitimately taken — by us. Reporting that as a collision made the
# normal case fail, and there was nothing to "stop first": `docker compose up -d`
# on a container that is already up is a no-op.
#
# Asked of the container by name rather than of the port, because the port says
# too little: Docker publishes every container's ports through one proxy process,
# so "com.docker.backend owns it" means some container does — not which one, and
# another project's PostgreSQL on this port is still the collision worth refusing.
db_container_publishes() {
  command -v docker >/dev/null 2>&1 || return 1
  local published
  published="$(docker inspect -f \
    '{{if .State.Running}}{{range $port, $bindings := .NetworkSettings.Ports}}{{range $bindings}}{{.HostPort}} {{end}}{{end}}{{end}}' \
    tradingcenter-db 2>/dev/null || true)"
  [[ " $published " == *" $1 "* ]]
}

# Best-effort, for the message only: often empty, and that is fine.
port_owner() {
  local pid
  pid="$(lsof -nP -iTCP:"$1" -sTCP:LISTEN -t 2>/dev/null | head -1 || true)"
  [[ -z "$pid" ]] && return 1
  printf ' by %s (pid %s)' "$(ps -p "$pid" -o comm= 2>/dev/null || echo process)" "$pid"
}

DB_ALREADY_RUNNING=0

ports=("$GATEWAY_PORT" "$ARCHIVE_PORT" "$DB_PORT")
(( START_TERMINAL )) && ports+=("$TERMINAL_PORT")
for port in "${ports[@]}"; do
  port_in_use "$port" || continue
  if [[ "$port" == "$DB_PORT" ]] && db_container_publishes "$DB_PORT"; then
    # Ours, and already up. Reused rather than reported.
    DB_ALREADY_RUNNING=1
    continue
  fi
  owner="$(port_owner "$port" || true)"
  if [[ "$port" == "$DB_PORT" ]]; then
    problems+=("port $DB_PORT is already in use${owner}, and not by this repository's database container — it is the port that container needs. Set DB_PORT to something free (and match it in modules/market-data/.env).")
  else
    problems+=("port $port is already in use${owner} — stop it, or it is a leftover run")
  fi
done

# The quiet disaster this guards against: the container comes up on 5433, the
# archive's .env still points at 5432, and everything then runs happily against
# whatever PostgreSQL the machine already had — migrations included. Nothing
# fails, and the data goes somewhere nobody meant.
archive_db_port="$(sed -n 's|^DATABASE_URL=.*:\([0-9][0-9]*\)/.*|\1|p' "$ARCHIVE_DIR/.env" 2>/dev/null | head -1)"
if [[ -n "$archive_db_port" && "$archive_db_port" != "$DB_PORT" ]]; then
  problems+=("modules/market-data/.env points DATABASE_URL at port $archive_db_port, but this script starts the database on $DB_PORT — it would migrate and fill a different database than the one it started")
fi

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
  if (( ${DB_STARTED:-0} )); then
    note "The database is still running — 'docker compose down' when you are done with it."
  fi
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

# --- the database -------------------------------------------------------------

if (( FRESH )); then
  say "Removing the existing database volume..."
  docker compose -f "$REPO_ROOT/compose.yaml" down -v >/dev/null 2>&1 || true
  DB_ALREADY_RUNNING=0
fi

# Run either way: `up -d` on a running container is a no-op, and on one whose
# definition has changed since it started it is the thing that reconciles it.
if (( DB_ALREADY_RUNNING )); then
  say "Reusing the database container already running on 127.0.0.1:$DB_PORT..."
else
  say "Starting PostgreSQL in a container..."
fi
if ! DB_PORT="$DB_PORT" docker compose -f "$REPO_ROOT/compose.yaml" up -d db; then
  fail "docker compose could not start the database."
  note "The reason is the line above. The two usual ones: the Docker daemon is not"
  note "running ('docker info' will say), or something already holds port $DB_PORT."
  DB_STARTED=0
  exit 1
fi
DB_STARTED=1

say "Waiting for it to accept connections..."
deadline=$((SECONDS + 60))
until [[ "$(docker inspect -f '{{.State.Health.Status}}' tradingcenter-db 2>/dev/null || echo missing)" == "healthy" ]]; do
  if (( SECONDS >= deadline )); then
    fail "the database did not become healthy within 60s."
    docker compose -f "$REPO_ROOT/compose.yaml" logs --tail 30 db || true
    exit 1
  fi
  sleep 1
done
ok "PostgreSQL is accepting connections on 127.0.0.1:$DB_PORT."

# Applied every run, not only on a fresh one: a checkout that has just pulled a
# new migration is exactly the case where forgetting this produces an error that
# reads like a bug in the archive.
say "Applying migrations..."
if ! ( cd "$ARCHIVE_DIR" && uv run alembic upgrade head ); then
  fail "migrations failed — the archive would fail on its first query, so stopping here."
  exit 1
fi
ok "Schema is up to date."

# --- capital-gateway ----------------------------------------------------------

say "Starting capital-gateway on port $GATEWAY_PORT..."
run_service "gateway " "$BLUE" "$GATEWAY_DIR" uv run uvicorn capital_gateway.app:app --reload --port "$GATEWAY_PORT"
wait_for_http "$GATEWAY_URL/capabilities" "capital-gateway" || exit 1
ok "capital-gateway is answering."

# --- market-data --------------------------------------------------------------
#
# After the gateway, because it subscribes to it as it starts. Before the
# terminal, because the terminal's charts read it.

say "Starting market-data on port $ARCHIVE_PORT..."
run_service "archive " "$MAGENTA" "$ARCHIVE_DIR" uv run uvicorn market_data.app:app --reload --port "$ARCHIVE_PORT"
wait_for_http "$ARCHIVE_URL/health" "market-data" || exit 1
ok "market-data is answering."

# --- the terminal -------------------------------------------------------------

if (( START_TERMINAL )); then
  say "Starting the terminal on port $TERMINAL_PORT..."
  run_service "terminal" "$CYAN" "$TERMINAL_DIR" "${TERMINAL_RUN[@]}"
fi

echo
ok "Ready:"
if (( START_TERMINAL )); then
  echo "  Terminal            http://localhost:$TERMINAL_PORT"
  echo "  Archive panel       http://localhost:$TERMINAL_PORT/archive"
fi
echo "  market-data docs    $ARCHIVE_URL/docs"
echo "  Gateway docs        $GATEWAY_URL/docs"
echo "  Database            postgresql://market_data:change-me@127.0.0.1:$DB_PORT/market_data"
echo
note "Nothing is archived until a pair is added in the Archive panel — that is deliberate."
note "Ctrl+C to stop the services. The database keeps running."
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
