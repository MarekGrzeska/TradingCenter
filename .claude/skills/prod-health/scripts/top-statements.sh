#!/usr/bin/env bash
# The statements loading the production database, from pg_stat_statements — ONLY on the operator's explicit yes.
# Opens a temporary firewall rule for this machine's public address and deletes it on any exit. psql runs inside
# the dev database container as a client only; the dev database itself is not touched.
#
#   bash .claude/skills/prod-health/scripts/top-statements.sh [limit=10]
set -euo pipefail
export MSYS_NO_PATHCONV=1

LIMIT="${1:-10}"
RG=rg-tradingcenter
SERVER=psql-tradingcenter
HOST="$SERVER.postgres.database.azure.com"
RULE="tmp-prod-health-$(date -u +%Y%m%d%H%M)"

[ -n "$(docker ps -q -f name=tradingcenter-db)" ] || { echo "the dev database container is not running (it supplies psql)"; exit 1; }
IP=$(curl -s https://api.ipify.org | tr -d '\r')
ADMIN=$(az postgres flexible-server microsoft-entra-admin list -g "$RG" -s "$SERVER" \
  --query "[0].principalName" -o tsv 2>/dev/null | tr -d '\r')

cleanup() {
  az postgres flexible-server firewall-rule delete -g "$RG" -n "$SERVER" --rule-name "$RULE" --yes -o none 2>/dev/null \
    && echo "firewall rule $RULE deleted" || echo "FIREWALL RULE $RULE MAY STILL EXIST — delete it by hand"
}
az postgres flexible-server firewall-rule create -g "$RG" -n "$SERVER" --rule-name "$RULE" \
  --start-ip-address "$IP" --end-ip-address "$IP" -o none 2>/dev/null
trap cleanup EXIT
echo "firewall rule $RULE open for $IP"

export PGPASSWORD
PGPASSWORD=$(az account get-access-token --resource https://ossrdbms-aad.database.windows.net \
  --query accessToken -o tsv | tr -d '\r')

psqlc() {
  docker exec -i -e PGPASSWORD tradingcenter-db \
    psql "host=$HOST port=5432 dbname=postgres user=$ADMIN sslmode=require" -v ON_ERROR_STOP=1 "$@"
}

echo "== since $(psqlc -At -c "select stats_reset from pg_stat_statements_info")"
echo "== by total time"
psqlc -c "select d.datname as db, s.calls, round(s.total_exec_time)::bigint as total_ms,
                 round(s.mean_exec_time::numeric, 2) as mean_ms, s.rows,
                 left(regexp_replace(s.query, '\s+', ' ', 'g'), 100) as statement
            from pg_stat_statements s join pg_database d on d.oid = s.dbid
           order by s.total_exec_time desc limit $LIMIT"
echo "== by calls"
psqlc -c "select d.datname as db, s.calls, round(s.total_exec_time)::bigint as total_ms,
                 left(regexp_replace(s.query, '\s+', ' ', 'g'), 100) as statement
            from pg_stat_statements s join pg_database d on d.oid = s.dbid
           order by s.calls desc limit $LIMIT"
