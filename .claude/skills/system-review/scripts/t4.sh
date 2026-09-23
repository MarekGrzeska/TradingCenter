#!/usr/bin/env bash
# Tier T4 of the system review: production statistics, read-only, and only on the operator's explicit yes.
# Opens a temporary firewall rule for this machine's public IP, snapshots pg_stat_database and
# pg_stat_user_tables in every database twice, MINUTES apart, removes the rule on any exit, and prints
# per-minute deltas. psql runs in a container as a client only; the operator's dev database is not touched.
#
#   bash .claude/skills/system-review/scripts/t4.sh <out-dir> [minutes=10]
#
# It sleeps for MINUTES, so start it in the background and let the agents work meanwhile.
set -euo pipefail
# Git Bash rewrites an argument starting with /subscriptions/ into a Windows path without this.
export MSYS_NO_PATHCONV=1

OUT="$1"
MINUTES="${2:-10}"
RG=rg-tradingcenter
SERVER=psql-tradingcenter
HOST="$SERVER.postgres.database.azure.com"
RULE="tmp-system-review-$(date -u +%Y%m%d%H%M)"
mkdir -p "$OUT"

# `az ... -o tsv` ends its lines with \r on Windows; every captured value is stripped of it.
IP=$(curl -s https://api.ipify.org | tr -d '\r')
ADMIN=$(az postgres flexible-server microsoft-entra-admin list -g "$RG" -s "$SERVER" \
  --query "[0].principalName" -o tsv | tr -d '\r')

cleanup() {
  az postgres flexible-server firewall-rule delete -g "$RG" -n "$SERVER" --rule-name "$RULE" --yes -o none 2>/dev/null \
    && echo "firewall rule $RULE deleted" || echo "FIREWALL RULE $RULE MAY STILL EXIST — delete it by hand"
}
az postgres flexible-server firewall-rule create -g "$RG" -n "$SERVER" --rule-name "$RULE" \
  --start-ip-address "$IP" --end-ip-address "$IP" -o none 2>/dev/null
trap cleanup EXIT
echo "firewall rule $RULE open for this machine"

psqlc() {
  if [ -n "$(docker ps -q -f name=tradingcenter-db)" ]; then
    docker exec -i -e PGPASSWORD tradingcenter-db \
      psql "host=$HOST port=5432 dbname=$1 user=$ADMIN sslmode=require" -At -F $'\t' -v ON_ERROR_STOP=1
  else
    docker run --rm -i -e PGPASSWORD postgres:17-alpine \
      psql "host=$HOST port=5432 dbname=$1 user=$ADMIN sslmode=require" -At -F $'\t' -v ON_ERROR_STOP=1
  fi
}

snapshot() {
  local label="$1"
  PGPASSWORD=$(az account get-access-token --resource-type oss-rdbms --query accessToken -o tsv | tr -d '\r')
  export PGPASSWORD
  local dbs
  dbs=$(echo "SELECT datname FROM pg_database WHERE NOT datistemplate AND datname NOT IN ('azure_maintenance','azure_sys') ORDER BY 1" \
    | psqlc postgres | tr -d '\r')
  echo "SELECT datname, now(), xact_commit, tup_returned, tup_fetched, tup_inserted, tup_updated, tup_deleted,
               blks_read, blks_hit, pg_database_size(datname)
          FROM pg_stat_database WHERE datname = ANY(string_to_array('$(echo $dbs | tr ' ' ',')', ','));" \
    | psqlc postgres > "$OUT/t4-$label-db.tsv"
  : > "$OUT/t4-$label-tables.tsv"
  for db in $dbs; do
    echo "SELECT current_database(), now(), relname, seq_scan, seq_tup_read, coalesce(idx_scan,0), coalesce(idx_tup_fetch,0),
                 n_tup_ins, n_tup_upd, n_tup_del, n_live_tup, n_dead_tup, pg_total_relation_size(relid)
            FROM pg_stat_user_tables;" | psqlc "$db" >> "$OUT/t4-$label-tables.tsv"
  done
  echo "snapshot $label at $(date -u +%H:%M:%SZ)"
}

snapshot first
sleep "$((MINUTES * 60))"
snapshot second

python - "$OUT" <<'EOF'
import sys
from datetime import datetime

out = sys.argv[1]


def load(name, key):
    rows = {}
    for line in open(f"{out}/{name}", encoding="utf-8"):
        cells = line.rstrip("\r\n").split("\t")
        if len(cells) > 3:
            rows[key(cells)] = cells
    return rows


def number(value):
    return int(value) if value.lstrip("-").isdigit() else 0


first, second = load("t4-first-db.tsv", lambda c: c[0]), load("t4-second-db.tsv", lambda c: c[0])
stamp = lambda c: datetime.fromisoformat(c[1].replace(" ", "T")[:26])
seconds = (stamp(next(iter(second.values()))) - stamp(next(iter(first.values())))).total_seconds()
per_minute = lambda a, b, i: (number(b[i]) - number(a[i])) * 60 / seconds
print(f"== per database, per minute, over {seconds:.0f} s")
print(f"{'database':14}{'commits':>10}{'returned':>13}{'fetched':>11}{'ins':>7}{'upd':>7}{'del':>7}{'size MB':>10}")
for db, b in second.items():
    a = first.get(db)
    if a:
        print(f"{db:14}{per_minute(a, b, 2):10.0f}{per_minute(a, b, 3):13,.0f}{per_minute(a, b, 4):11,.0f}"
              f"{per_minute(a, b, 5):7.0f}{per_minute(a, b, 6):7.0f}{per_minute(a, b, 7):7.0f}{number(b[10]) / 1e6:10.1f}")
tables_a = load("t4-first-tables.tsv", lambda c: (c[0], c[2]))
tables_b = load("t4-second-tables.tsv", lambda c: (c[0], c[2]))
rows = []
for key, b in tables_b.items():
    a = tables_a.get(key)
    if a:
        rows.append((key, *(per_minute(a, b, i) for i in (3, 4, 5, 6, 7, 8, 9)), number(b[10]), number(b[12])))
print("\n== tables by rows read per minute (sequential + index)")
print(f"{'database.table':42}{'seq':>8}{'seq rows':>12}{'idx':>8}{'idx rows':>11}{'ins':>7}{'upd':>7}{'del':>7}{'live':>12}{'MB':>9}")
for row in sorted(rows, key=lambda r: -(r[2] + r[4]))[:15]:
    (db, table), seq, seq_rows, idx, idx_rows, ins, upd, dele, live, size = row
    print(f"{db + '.' + table:42}{seq:8.1f}{seq_rows:12,.0f}{idx:8.1f}{idx_rows:11,.0f}{ins:7.1f}{upd:7.1f}{dele:7.1f}{live:12,}{size / 1e6:9.1f}")
EOF
