#!/usr/bin/env bash
#
# Everything the terminal needs, in the order it needs it — the macOS and Linux
# counterpart of dev.ps1.
#
#   migrations -> capital-gateway -> market-data -> market-mcp -> trading-mcp -> teams
#   -> teams-mcp -> agent -> terminal
#
# The order is not tidiness, and every arrow in it is now a real dependency.
# market-data opens a subscription per tracked pair the moment it starts, so a gateway
# that is not listening yet costs it a round of backoff; market-mcp reads market-data's
# own contract; trading-mcp asks the gateway whether it is bound to the demo account and
# refuses to open a port at all if it is not, so a gateway that is not answering yet is a
# module that exits rather than waits; the agent asks market-mcp for its tool list on the
# first turn, and a market-mcp that was not up yet means an agent answering without tools
# rather than an error anyone would notice; teams reads both tool lists for the agents a
# run assigns tools to; the terminal's charts read the archive, so starting it first fills
# the console with proxy errors that mean nothing. Each step waits for the one before it
# to actually answer, not merely to have been launched.
#
# market-mcp needs no .env of its own to run here: every setting it reads has a
# working default for loopback (`config.py`), unlike the gateway and the archive,
# which hold real credentials with no safe default to fall back to. trading-mcp is the
# other kind: the gateway checks its `X-Gateway-Key` on every caller, loopback included,
# so this one module has a credential to fill in even locally.
#
# The database is the container in ../compose.yaml — started here, before migrations
# (openspec/changes/local-dev-database-in-docker; the spell in Azure is over, production
# stays there and development does not). `docker compose down` keeps the data.
#
# `agent`'s and `teams`' own databases are further logical databases in that same
# container, created here if missing rather than through docker-entrypoint-initdb.d —
# that only runs on a volume's first boot, so it would never fire for anyone who already
# has tradingcenter-db-data from before either module existed (design.md, "Baza: druga
# baza logiczna, jeden serwer"). Three databases, one server, the same shape production
# has.
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
MCP_DIR="$REPO_ROOT/modules/market-mcp"
TRADING_DIR="$REPO_ROOT/modules/trading-mcp"
AGENT_DIR="$REPO_ROOT/modules/agent"
TEAMS_DIR="$REPO_ROOT/modules/teams"
TEAMS_MCP_DIR="$REPO_ROOT/modules/teams-mcp"
TERMINAL_DIR="$REPO_ROOT/modules/terminal"

GATEWAY_PORT=8010
ARCHIVE_PORT=8020
AGENT_PORT=8030
MCP_PORT=8040
TEAMS_PORT=8050
TRADING_PORT=8060
TEAMS_MCP_PORT=8070
TERMINAL_PORT=5173

# 127.0.0.1 rather than "localhost": uvicorn binds IPv4 loopback, and on a machine
# where "localhost" resolves to ::1 first the wait below would never succeed.
GATEWAY_URL="http://127.0.0.1:$GATEWAY_PORT"
ARCHIVE_URL="http://127.0.0.1:$ARCHIVE_PORT"
AGENT_URL="http://127.0.0.1:$AGENT_PORT"
MCP_URL="http://127.0.0.1:$MCP_PORT"
TEAMS_URL="http://127.0.0.1:$TEAMS_PORT"
TRADING_URL="http://127.0.0.1:$TRADING_PORT"
TEAMS_MCP_URL="http://127.0.0.1:$TEAMS_MCP_PORT"

START_TERMINAL=1
WAIT_SECONDS=120

for arg in "$@"; do
  case "$arg" in
    --no-terminal) START_TERMINAL=0 ;;
    -h|--help) sed -n '2,42p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $arg (try --help)" >&2; exit 2 ;;
  esac
done

BLUE=$'\033[34m'; MAGENTA=$'\033[35m'; CYAN=$'\033[36m'; YELLOW=$'\033[33m'
GREEN=$'\033[32m'; RED=$'\033[31m'; DIM=$'\033[2m'; RESET=$'\033[0m'
# Bright blue for teams — six services now, and the six basic colours were spoken for.
BRIGHT_BLUE=$'\033[94m'
# And bright green for trading-mcp, deliberately a shade of market-mcp's own: the two
# tool servers read as a pair in the log, which is what they are.
BRIGHT_GREEN=$'\033[92m'
# And bright magenta for teams-mcp — the third tool server, and the only one that carries
# somebody's own credential rather than a module's.
BRIGHT_MAGENTA=$'\033[95m'

say()  { printf '%s%s%s\n' "$CYAN" "$1" "$RESET"; }
ok()   { printf '%s%s%s\n' "$GREEN" "$1" "$RESET"; }
fail() { printf '%s%s%s\n' "$RED" "$1" "$RESET" >&2; }
note() { printf '%s%s%s\n' "$DIM" "$1" "$RESET"; }

# --- what has to be true before anything starts -------------------------------
#
# Checked up front and reported together. Finding out about a missing .env after
# two services are already running means killing them to fix one line.

problems=()

command -v uv >/dev/null 2>&1 || problems+=("uv is not on PATH (runs all three Python services) — https://docs.astral.sh/uv/")

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
# teams needs a key and a MODELS catalogue: config.py refuses to build Settings without
# either, so the module would exit at import rather than start and misbehave.
[[ -f "$TEAMS_DIR/.env" ]] || problems+=("$TEAMS_DIR/.env is missing — copy .env.example and fill in OPENAI_API_KEY (MODELS has a working default there)")
# trading-mcp cannot fall back the way market-mcp does: `config.py` requires the
# gateway's caller key, and the gateway checks it on loopback too.
[[ -f "$TRADING_DIR/.env" ]] || problems+=("$TRADING_DIR/.env is missing — copy .env.example and set CAPITAL_GATEWAY_API_KEY to the gateway's own GATEWAY_API_KEY")

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

ports=("$GATEWAY_PORT" "$ARCHIVE_PORT" "$MCP_PORT" "$TRADING_PORT" "$TEAMS_MCP_PORT" "$AGENT_PORT" "$TEAMS_PORT")
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

teams_db_host="$(sed -n 's|^DATABASE_URL=[a-z+]*://\([^@/]*@\)\{0,1\}\([^:/?]*\).*|\2|p' "$TEAMS_DIR/.env" 2>/dev/null | head -1)"
case "$teams_db_host" in
  ""|localhost|127.*|::1) ;;
  *) problems+=("modules/teams/.env's DATABASE_URL points at '$teams_db_host' — local runs use the compose.yaml container (localhost), never a remote database") ;;
esac

# The two halves of one credential, in two files. The gateway checks `X-Gateway-Key` on
# every caller including loopback, and trading-mcp asks it about the account *before* it
# opens a port — so a mismatch here is not a failed tool call later, it is a module that
# exits during start-up and takes this whole script down with it. Cheap to compare, and
# the message is the fix.
gateway_key="$(sed -n 's|^GATEWAY_API_KEY=\(.*\)|\1|p' "$GATEWAY_DIR/.env" 2>/dev/null | head -1)"
trading_key="$(sed -n 's|^CAPITAL_GATEWAY_API_KEY=\(.*\)|\1|p' "$TRADING_DIR/.env" 2>/dev/null | head -1)"
if [[ -n "$gateway_key" && -n "$trading_key" && "$gateway_key" != "$trading_key" ]]; then
  problems+=("modules/trading-mcp/.env's CAPITAL_GATEWAY_API_KEY does not match modules/capital-gateway/.env's GATEWAY_API_KEY — trading-mcp would be refused by the gateway and exit before it listens")
elif [[ -z "$trading_key" ]]; then
  problems+=("modules/trading-mcp/.env has no CAPITAL_GATEWAY_API_KEY — the gateway requires it from every caller, loopback included")
fi

if (( ${#problems[@]} )); then
  fail "Cannot start:"
  for problem in "${problems[@]}"; do fail "  - $problem"; done
  exit 1
fi

# Not a problem — an agent without tools is a supported state, and the one it degrades
# to when market-mcp is down. It is worth saying out loud, though: an `.env` written
# before the tools existed leaves the agent answering from the model alone, which looks
# from the panel exactly like tools that are broken.
if ! grep -qs '^MARKET_MCP_URL=..*' "$AGENT_DIR/.env"; then
  note "modules/agent/.env has no MARKET_MCP_URL — the agent will run without tools."
  note "  Add MARKET_MCP_URL=$MCP_URL to give it market-mcp's, as .env.example does."
fi

# Same for teams, with a sharper edge: the agent without a tool server answers from the
# model alone, while a team whose agents were *assigned* tools refuses to run at all
# (specs/teams-tool-access). Both are supported states; only one of them looks like the
# module is broken.
if ! grep -qs '^MARKET_MCP_URL=..*' "$TEAMS_DIR/.env"; then
  note "modules/teams/.env has no MARKET_MCP_URL — teams whose agents assign tools will refuse to run."
  note "  Add MARKET_MCP_URL=$MCP_URL to give it market-mcp's, as .env.example does."
fi

# The same again for the write half, and it is the one worth saying twice: a team given
# only reading tools runs perfectly without this line, so its absence shows up as a
# refusal on the one run that was supposed to place an order.
if ! grep -qs '^TRADING_MCP_URL=..*' "$TEAMS_DIR/.env"; then
  note "modules/teams/.env has no TRADING_MCP_URL — teams will have no order tools, and one assigning them refuses to run."
  note "  Add TRADING_MCP_URL=$TRADING_URL to give it trading-mcp's, as .env.example does."
fi

# The agent's second tool server. Its absence is a supported state exactly like
# MARKET_MCP_URL's — the agent works and simply has no team tools — but the symptom is
# confusing enough to be worth a line: the operator asks for a team, and the agent
# explains that it cannot do that, which reads like a missing feature rather than a
# missing setting.
if ! grep -qs '^TEAMS_MCP_URL=..*' "$AGENT_DIR/.env"; then
  note "modules/agent/.env has no TEAMS_MCP_URL — the agent will have no tools for building or running teams."
  note "  Add TEAMS_MCP_URL=$TEAMS_MCP_URL to give it teams-mcp's, as .env.example does."
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

ensure_database() {
  local name="$1"
  if ! psql_super -tAc "SELECT 1 FROM pg_roles WHERE rolname = '$name'" | grep -q 1; then
    psql_super -c "CREATE ROLE $name LOGIN PASSWORD 'change-me';" || { fail "could not create the '$name' role"; exit 1; }
  fi
  if ! psql_super -tAc "SELECT 1 FROM pg_database WHERE datname = '$name'" | grep -q 1; then
    psql_super -c "CREATE DATABASE $name OWNER $name;" || { fail "could not create the '$name' database"; exit 1; }
  fi
}

say "Ensuring the agent and teams databases exist..."
ensure_database agent
ensure_database teams
ok "agent and teams databases are ready."

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
if ! ( cd "$TEAMS_DIR" && uv run alembic upgrade head ); then
  fail "teams' migrations failed — it would fail on its first query, so stopping here."
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

# --- market-mcp -----------------------------------------------------------------
#
# After market-data, whose contract it reads. No `--reload`: unlike the other
# services this one is not started through uvicorn's own CLI (`server.py`'s
# caller-identity wrapper needs the ASGI app built in Python first), so a code
# change here needs a manual restart for now.

say "Starting market-mcp on port $MCP_PORT..."
run_service "mcp     " "$GREEN" "$MCP_DIR" uv run python -m market_mcp http
wait_for_http "$MCP_URL/health" "market-mcp" || exit 1
ok "market-mcp is answering."

# --- trading-mcp ------------------------------------------------------------------
#
# After the gateway, and this one is not a preference: `__main__.py` asks
# `GET /capabilities` and refuses to open a port unless the answer says `demo`
# (specs/trading-mcp-upstream-access). A gateway that is not answering yet is therefore a
# module that exits rather than one that retries — which the watchdog at the bottom of
# this script reports as "A service exited", and it would be telling the truth.
#
# No `--reload`, same as market-mcp: the ASGI app is built in Python (the caller-identity
# wrapper), not handed to uvicorn's CLI, so a code change here needs a restart.

say "Starting trading-mcp on port $TRADING_PORT..."
run_service "trading " "$BRIGHT_GREEN" "$TRADING_DIR" uv run python -m trading_mcp
wait_for_http "$TRADING_URL/health" "trading-mcp" || exit 1
ok "trading-mcp is answering."

# --- agent ----------------------------------------------------------------------
#
# Last among the back ends: nothing else calls it, so nothing else waits on it —
# unlike the gateway, which market-data subscribes to as it starts. It does call
# market-mcp, which is why it starts after it: the tool list is read on the first
# turn, and a market-mcp still coming up would mean a turn answered without tools.

say "Starting agent on port $AGENT_PORT..."
run_service "agent   " "$YELLOW" "$AGENT_DIR" uv run uvicorn agent.app:app --reload --port "$AGENT_PORT"
wait_for_http "$AGENT_URL/health" "agent" || exit 1
ok "agent is answering."

# --- teams ------------------------------------------------------------------------
#
# After market-mcp for the same reason the agent is, and after the agent for no reason
# at all beyond a fixed order: nothing calls teams, and teams calls nobody the agent
# does not. The two are siblings, not a chain.

say "Starting teams on port $TEAMS_PORT..."
run_service "teams   " "$BRIGHT_BLUE" "$TEAMS_DIR" uv run uvicorn teams.app:app --reload --port "$TEAMS_PORT"
wait_for_http "$TEAMS_URL/health" "teams" || exit 1
ok "teams is answering."

# --- teams-mcp --------------------------------------------------------------------
#
# After teams, because its tools are teams' catalogue — though it starts happily without
# it and reports the outage per call rather than refusing to run, which is market-mcp's
# shape and not trading-mcp's.
#
# Before nothing in particular: the agent asks it for its tool list on the first turn that
# wants one, not at start-up, so the order below is for a readable log rather than for
# correctness.

say "Starting teams-mcp on port $TEAMS_MCP_PORT..."
run_service "teamsmcp" "$BRIGHT_MAGENTA" "$TEAMS_MCP_DIR" uv run python -m teams_mcp
wait_for_http "$TEAMS_MCP_URL/health" "teams-mcp" || exit 1
ok "teams-mcp is answering."

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
echo "  market-mcp health   $MCP_URL/health"
echo "  trading-mcp health  $TRADING_URL/health"
echo "  agent docs          $AGENT_URL/docs"
echo "  teams docs          $TEAMS_URL/docs"
echo "  Database            market_data, agent, teams @ localhost:55432 (compose.yaml; 'docker compose down' keeps the data)"
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
