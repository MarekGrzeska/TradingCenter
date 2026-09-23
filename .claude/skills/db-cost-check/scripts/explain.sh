#!/usr/bin/env bash
# EXPLAIN one statement on the dev database, twice: as the planner chooses, and with sequential scans off.
# Inside a transaction that is rolled back, so even a statement that writes changes nothing.
#
#   bash .claude/skills/db-cost-check/scripts/explain.sh <database> "<SQL>"
set -euo pipefail

DB="${1:?database: market_data agent teams polymarket social strategy telegram}"
SQL="${2:?the statement, with literals in place of parameters}"

if [ -z "$(docker ps -q -f name=tradingcenter-db)" ]; then
  echo "the dev database container is not running — this skill never starts it; run the stack first"
  exit 1
fi

# The container's superuser trusts its own socket, so no password; the database is the one named.
run() {
  docker exec -i tradingcenter-db psql -U market_data -d "$DB" -v ON_ERROR_STOP=1 -q "$@"
}

# count(*) is fine here and nowhere else: dev tables are small, and the statistics a planner reads are often reset.
echo "== rows in the tables it names (dev scale — production is usually far larger)"
tables=$(printf '%s' "$SQL" | grep -oiE '(from|join|into|update)[[:space:]]+[a-z_]+' | awk '{print tolower($2)}' | sort -u)
for t in $tables; do
  printf "  %-28s %s\n" "$t" "$(echo "SELECT count(*) FROM $t;" | run -At 2>/dev/null || echo '?')"
done

echo "== plan as chosen"
printf 'BEGIN;\nEXPLAIN (ANALYZE, BUFFERS, COSTS OFF) %s;\nROLLBACK;\n' "$SQL" | run

echo "== plan with enable_seqscan = off (could an index serve it?)"
printf 'BEGIN;\nSET LOCAL enable_seqscan = off;\nEXPLAIN (ANALYZE, BUFFERS, COSTS OFF) %s;\nROLLBACK;\n' "$SQL" | run
