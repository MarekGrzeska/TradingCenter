#!/bin/sh
# Every role and database the system needs, created if missing and left alone if present. Each role owns its database
# from the start, which is what lets a module migrate itself with no operator step in between — the
# `grant-schema-ownership.sql` of the Azure days has no counterpart here.
#
# Run by the `db-init` service on every deploy, as the server's superuser. A password changed in `.env` is applied here:
# the role's password is set each time, so rotating one is editing a secret and deploying.
set -eu

psql_q() { psql -v ON_ERROR_STOP=1 -qtAX "$@"; }

ensure() {
  name="$1"
  password="$2"
  [ -n "$password" ] || { echo "no password given for role $name" >&2; exit 1; }

  # The password goes in as a psql variable, quoted by psql itself, so a quote in it cannot end the statement. Through
  # stdin: `-c` does not interpolate variables, a script does.
  if [ "$(psql_q -d postgres -c "SELECT 1 FROM pg_roles WHERE rolname = '$name'")" != "1" ]; then
    echo "CREATE ROLE $name LOGIN PASSWORD :'pw'" | psql_q -d postgres -v pw="$password"
  else
    echo "ALTER ROLE $name PASSWORD :'pw'" | psql_q -d postgres -v pw="$password"
  fi
  if [ "$(psql_q -d postgres -c "SELECT 1 FROM pg_database WHERE datname = '$name'")" != "1" ]; then
    psql_q -d postgres -c "CREATE DATABASE $name OWNER $name"
  fi
  # Revoked from everyone else: PUBLIC may connect to a new database by default, and these hold one role's data.
  psql_q -d postgres -c "REVOKE ALL ON DATABASE $name FROM PUBLIC"
  psql_q -d postgres -c "GRANT ALL ON DATABASE $name TO $name"
  echo "database $name: ready"
}

# A database whose module is gone: dropped with its role, so no deploy is left holding data nothing reads. FORCE ends
# connections a stale container may still hold; the last nightly dump is the way back.
retire() {
  name="$1"
  psql_q -d postgres -c "DROP DATABASE IF EXISTS $name WITH (FORCE)"
  psql_q -d postgres -c "DROP ROLE IF EXISTS $name"
  echo "database $name: retired"
}

ensure agent        "${AGENT_DB_PASSWORD:-}"
ensure teams        "${TEAMS_DB_PASSWORD:-}"
ensure market_data  "${MARKET_DB_PASSWORD:-}"
ensure polymarket   "${POLYMARKET_DB_PASSWORD:-}"
ensure social       "${SOCIAL_DB_PASSWORD:-}"
ensure telegram     "${TELEGRAM_DB_PASSWORD:-}"
ensure youtube      "${YOUTUBE_DB_PASSWORD:-}"

retire strategy

# Where the operator asks what loads the server (`prod-health`): the statistics are cluster-wide, the view is per database.
psql_q -d postgres -c "CREATE EXTENSION IF NOT EXISTS pg_stat_statements"
echo "pg_stat_statements: ready"
