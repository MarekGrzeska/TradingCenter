#!/bin/sh
# One dump of every database, into BACKUP_DIR, and the old ones removed. Run nightly from cron as the deploying user.
#
# A dump is written under a name that is not a dump yet and renamed when it is whole, so neither `backup-serve` nor the
# retention below ever sees half of one. A database that fails is named in an alert and does not stop the others —
# the next night's dump of it is not made less important by tonight's failure of its neighbour.
#
# `PG_EXEC` is how a command reaches the database server; by default the compose service's `postgres` container, and a test
# points it at anything that behaves like `pg_dump`'s host.
set -u
umask 027

APP_DIR="${APP_DIR:-/opt/tradingcenter}"
# Outside /opt/tradingcenter, whose mode keeps every other account out: the backup account reads this directory and no other.
BACKUP_DIR="${BACKUP_DIR:-/var/backups/tradingcenter}"
KEEP_DAYS="${KEEP_DAYS:-14}"
DATABASES="${DATABASES:-agent teams market_data polymarket social telegram youtube}"
PROJECT="${COMPOSE_PROJECT:-tradingcenter-vps}"
PG_EXEC="${PG_EXEC:-docker compose --project-name $PROJECT --env-file $APP_DIR/.env --env-file $APP_DIR/tags.env -f $APP_DIR/docker-compose.yml exec -T postgres}"
ALERT="${ALERT:-$(dirname "$0")/alert}"

mkdir -p "$BACKUP_DIR"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
failed=""

for db in $DATABASES; do
  partial="$BACKUP_DIR/.${db}-${stamp}.partial"
  final="$BACKUP_DIR/${db}-${stamp}.dump"
  # Custom format: compressed, and `pg_restore` can take one table out of it.
  # shellcheck disable=SC2086
  if $PG_EXEC pg_dump -U postgres -Fc "$db" > "$partial" && [ -s "$partial" ]; then
    mv "$partial" "$final"
    echo "backup: $db -> $(basename "$final") ($(wc -c < "$final") bytes)"
  else
    rm -f "$partial"
    failed="$failed $db"
    echo "backup: $db FAILED" >&2
  fi
done

# Retention: older than KEEP_DAYS go, but the newest dump of each database never does — a week of failed nights must not
# empty the directory of the last good one.
for db in $DATABASES; do
  # Newest first, and the first is skipped: whatever else its age, it is the last good dump of that database.
  ls -1t "$BACKUP_DIR/${db}-"*.dump 2>/dev/null | tail -n +2 | while IFS= read -r old; do
    if [ -n "$(find "$old" -maxdepth 0 -mtime "+${KEEP_DAYS}")" ]; then
      rm -f "$old"
      echo "backup: removed $(basename "$old")"
    fi
  done
done

if [ -n "$failed" ]; then
  "$ALERT" "backup failed for:$failed" || true
  exit 1
fi
