#!/bin/sh
# Said once a day, in the morning: is there a dump of every database from the last day, and has the operator's computer
# collected any in the last three? Two alerts, because they fail separately — the first is the server's own job, the
# second is the only way the server learns that its copies never left it.
set -u

APP_DIR="${APP_DIR:-/opt/tradingcenter}"
# Outside /opt/tradingcenter, whose mode keeps every other account out: the backup account reads this directory and no other.
BACKUP_DIR="${BACKUP_DIR:-/var/backups/tradingcenter}"
ACK_FILE="${ACK_FILE:-/var/lib/tradingcenter/backup-ack/last-ack}"
DATABASES="${DATABASES:-agent teams market_data polymarket social telegram youtube alerts}"
DUMP_MAX_AGE_MINUTES="${DUMP_MAX_AGE_MINUTES:-1560}"  # a day and two hours: the night's run may be slow
ACK_MAX_AGE_MINUTES="${ACK_MAX_AGE_MINUTES:-4320}"    # three days
ALERT="${ALERT:-$(dirname "$0")/alert}"

missing=""
for db in $DATABASES; do
  recent="$(find "$BACKUP_DIR" -maxdepth 1 -name "${db}-*.dump" -mmin "-${DUMP_MAX_AGE_MINUTES}" 2>/dev/null | head -n 1)"
  [ -n "$recent" ] || missing="$missing $db"
done

problems=""
[ -z "$missing" ] || problems="no dump from the last day for:$missing"

# Never collected is judged by the oldest dump we hold: a fresh server that has not been pulled from yet is not an emergency
# until three days have gone by.
if [ -f "$ACK_FILE" ]; then
  stale="$(find "$ACK_FILE" -mmin "+${ACK_MAX_AGE_MINUTES}" 2>/dev/null)"
else
  stale="$(find "$BACKUP_DIR" -maxdepth 1 -name '*.dump' -mmin "+${ACK_MAX_AGE_MINUTES}" 2>/dev/null | head -n 1)"
fi
if [ -n "$stale" ]; then
  [ -z "$problems" ] || problems="$problems; "
  problems="${problems}the operator's computer has collected no backups for 3 days, so they exist only on this server"
fi

[ -z "$problems" ] && exit 0
"$ALERT" "$problems"
