#!/bin/sh
# Tells the operator when the disk holding the application is fuller than DISK_ALERT_PERCENT (default 80), at most once a
# day: a full disk is a slow emergency and a message every hour for it is how messages get muted.
set -eu
threshold="${DISK_ALERT_PERCENT:-80}"
dir="${APP_DIR:-/opt/tradingcenter}"
stamp="${dir}/.disk-alert-sent"

used="$(df --output=pcent "$dir" | tail -n 1 | tr -dc '0-9')"
[ "$used" -lt "$threshold" ] && { rm -f "$stamp"; exit 0; }

# Already said today.
if [ -f "$stamp" ] && [ -n "$(find "$stamp" -mmin -1440 2>/dev/null)" ]; then
  exit 0
fi
"$(dirname "$0")/alert" "disk is ${used}% full (alert at ${threshold}%)"
touch "$stamp"
