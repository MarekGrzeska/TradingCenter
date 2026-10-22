#!/bin/sh
# One message to the operator, straight to Telegram's Bot API: `alert.sh "text"`.
#
# Not through the workbench's `/telegram`, which is the door every other alert uses: a cron job on the host has no
# Entra token to present, and the alerts this sends — no backup, a full disk — are about the very state in which the
# workbench may not answer. Credentials live in /opt/tradingcenter/alert.env (mode 600, written by the deploy from
# secrets): ALERT_BOT_TOKEN and ALERT_CHAT_ID. Without them the message goes to the journal and the job still fails.
set -eu
text="${1:?usage: alert.sh <text>}"
env_file="${ALERT_ENV_FILE:-/opt/tradingcenter/alert.env}"

if [ -r "$env_file" ]; then
  # shellcheck disable=SC1090
  . "$env_file"
fi
host="$(hostname)"
logger -t tradingcenter-alert "$text" || true

if [ -z "${ALERT_BOT_TOKEN:-}" ] || [ -z "${ALERT_CHAT_ID:-}" ]; then
  echo "alert not sent (no ALERT_BOT_TOKEN / ALERT_CHAT_ID): $text" >&2
  exit 1
fi

# The token is in the URL by Telegram's design; `--fail` and no `-v`, so neither a refusal nor a trace prints it.
curl --silent --show-error --fail --max-time 20 \
  --data-urlencode "chat_id=${ALERT_CHAT_ID}" \
  --data-urlencode "text=[${host}] ${text}" \
  "https://api.telegram.org/bot${ALERT_BOT_TOKEN}/sendMessage" >/dev/null
