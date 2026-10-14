#!/bin/sh
# The one command the `tcbackup` user's key (not `backup`, which Debian already has for its own purposes) may run: a read-only window onto the dumps. The operator's computer asks in
# SSH_ORIGINAL_COMMAND and nothing else is reachable with that key, whatever it asks for.
#
#   list          one line per dump: "<name> <bytes>"
#   get <name>    that dump, on stdout
#   ack           "I have collected what was listed" — the server's only evidence that its copies left it
set -eu

BACKUP_DIR="${BACKUP_DIR:-/var/backups/tradingcenter}"
ACK_FILE="${ACK_FILE:-/var/lib/tradingcenter/backup-ack/last-ack}"

read -r verb arg extra <<EOF_CMD
${SSH_ORIGINAL_COMMAND:-${1:-}} ${2:-}
EOF_CMD
: "${verb:?no command given}"

die() { echo "backup-serve: $*" >&2; exit 1; }

case "$verb" in
  list)
    for file in "$BACKUP_DIR"/*.dump; do
      [ -f "$file" ] || continue
      echo "$(basename "$file") $(wc -c < "$file" | tr -d ' ')"
    done
    ;;
  get)
    # A dump's name as `backup.sh` writes it, and nothing a path could be made of.
    case "$arg" in
      ""|*[!a-z0-9_.TZ-]*|.*|*..*) die "refused name" ;;
    esac
    case "$arg" in
      *.dump) ;;
      *) die "refused name" ;;
    esac
    [ -f "$BACKUP_DIR/$arg" ] || die "no such dump"
    cat "$BACKUP_DIR/$arg"
    ;;
  ack)
    mkdir -p "$(dirname "$ACK_FILE")"
    touch "$ACK_FILE"
    echo "ack: noted"
    ;;
  *) die "unknown command" ;;
esac
