#!/bin/bash
# Fills the GitHub environment `vps` with everything `deploy/env.required` names, so the deploy workflow has what it needs
# and nobody types a secret into a terminal, a chat or a file. Run from the repository root by the operator, logged in to
# `gh` (repository admin) and — while Azure still exists — to `az`:
#
#   deploy/scripts/fill-github-environment.sh --host 57.129.181.251 --deploy-key .local/keys/deploy_key
#
# Where each value comes from, and what is printed (names only, never a value):
#   generated here        the database passwords, the superuser's, the key the services show one another. Set once and
#                         left alone on a re-run (`--rotate` regenerates them), because rotating a database password under
#                         a running stack is a deploy of its own.
#   Azure Key Vault       the provider keys the system already holds: capital.com, OpenAI (two), YouTube Data, Gemini.
#   the Azure app         the model catalogues, the default model, the alert destination — the live settings, so the new
#                         server starts with the configuration the old one ends with.
#   this repository       the Entra ids the terminal and the pocket are registered under (repository variables).
#   arguments             the address, the names to answer on, the deploy key.
#
# What it cannot know and leaves unset: ALERT_BOT_TOKEN, ALERT_CHAT_ID (the Telegram bot that tells you about disks and
# backups), and the Telegram account session. All three are optional.
set -euo pipefail

ENVIRONMENT=vps
HOST=""
DEPLOY_KEY=""
DOMAIN=""
ROTATE=0
VAULT="${KEY_VAULT_NAME:-kv-tradingctr-58hw}"
WEBAPP_RG="${AZURE_RESOURCE_GROUP:-rg-tradingcenter}"
WEBAPP="${AZURE_WORKBENCH_APP:-app-tradingcenter-agent}"

while [ $# -gt 0 ]; do
  case "$1" in
    --host) HOST="$2"; shift 2 ;;
    --deploy-key) DEPLOY_KEY="$2"; shift 2 ;;
    --domain) DOMAIN="$2"; shift 2 ;;
    --rotate) ROTATE=1; shift ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
[ -n "$HOST" ] && [ -n "$DEPLOY_KEY" ] || { echo "usage: $0 --host <ip> --deploy-key <private key file> [--domain <base domain>] [--rotate]" >&2; exit 2; }
[ -r "$DEPLOY_KEY" ] || { echo "cannot read $DEPLOY_KEY" >&2; exit 2; }

# MSYS_NO_PATHCONV: Git Bash on Windows rewrites an argument that looks like a path (`api://…`) before `az` sees it.
export MSYS_NO_PATHCONV=1
REPO="$(gh repo view --json nameWithOwner -q .nameWithOwner)"
OWNER_LC="$(echo "${REPO%%/*}" | tr '[:upper:]' '[:lower:]')"
REPO_LC="$(echo "$REPO" | tr '[:upper:]' '[:lower:]')"

# With no domain of one's own, sslip.io answers for any name under `<ip with dashes>.sslip.io` with that address — enough
# for Let's Encrypt to issue a certificate, and a stand-in until a real name exists.
if [ -z "$DOMAIN" ]; then
  DOMAIN="$(echo "$HOST" | tr . -).sslip.io"
fi

existing_secrets="$(gh secret list --env "$ENVIRONMENT" 2>/dev/null | cut -f1 || true)"
have_secret() { echo "$existing_secrets" | grep -qx "$1"; }

set_secret() {  # name, value on stdin
  # No `--body`: with a pipe on stdin `gh` reads the value from it, and the value never appears in a process list.
  gh secret set "$1" --env "$ENVIRONMENT" >/dev/null && echo "secret   $1"
}
set_variable() {  # name, value
  gh variable set "$1" --env "$ENVIRONMENT" --body "$2" >/dev/null && echo "variable $1"
}
# Not `tr … < /dev/urandom | head`: under `pipefail` the `tr` that `head` closes on is reported as a failure.
random_secret() { local s; s="$(head -c 100 /dev/urandom | base64 | tr -dc 'A-Za-z0-9')"; printf %s "${s:0:40}"; }
vault() { local v; v="$(az keyvault secret show --vault-name "$VAULT" --name "$1" --query value -o tsv | tr -d '\r')"; printf %s "$v"; }

gh api -X PUT "repos/$REPO/environments/$ENVIRONMENT" >/dev/null && echo "environment $ENVIRONMENT: ready"

# --- generated, once -----------------------------------------------------------------------------------------------------
for name in POSTGRES_PASSWORD AGENT_DB_PASSWORD TEAMS_DB_PASSWORD MARKET_DB_PASSWORD POLYMARKET_DB_PASSWORD \
            SOCIAL_DB_PASSWORD TELEGRAM_DB_PASSWORD YOUTUBE_DB_PASSWORD ALERTS_DB_PASSWORD GATEWAY_API_KEY; do
  if [ "$ROTATE" = 1 ] || ! have_secret "$name"; then
    random_secret | set_secret "$name"
  else
    echo "secret   $name (kept)"
  fi
done

# --- the deploy key ------------------------------------------------------------------------------------------------------
set_secret DEPLOY_SSH_KEY < "$DEPLOY_KEY"

# --- the provider keys the system already holds ---------------------------------------------------------------------------
declare -A FROM_VAULT=(
  [CAPITAL_API_KEY]=capital-api-key
  [CAPITAL_IDENTIFIER]=capital-identifier
  [CAPITAL_PASSWORD]=capital-password
  [AGENT_OPENAI_API_KEY]=openai-api-key
  [TEAMS_OPENAI_API_KEY]=teams-openai-api-key
  [YOUTUBE_DATA_API_KEY]=youtube-data-api-key
  [YOUTUBE_GEMINI_API_KEY]=gemini-api-key
)
for name in "${!FROM_VAULT[@]}"; do
  vault "${FROM_VAULT[$name]}" | set_secret "$name"
done

# --- the live configuration of the Azure workbench -----------------------------------------------------------------------
app_setting() {
  tr -d '\r' < <(az webapp config appsettings list -g "$WEBAPP_RG" -n "$WEBAPP" --query "[?name=='$1'].value | [0]" -o tsv)
}
for name in AGENT_MODELS TEAMS_MODELS AGENT_DEFAULT_MODEL_ID; do
  value="$(app_setting "$name")"
  [ -n "$value" ] || { echo "the Azure app has no $name; cannot copy it" >&2; exit 1; }
  set_variable "$name" "$value"
done

# --- public facts --------------------------------------------------------------------------------------------------------
repo_var() { gh variable list --json name,value -q ".[] | select(.name==\"$1\") | .value"; }
tenant="$(repo_var AZURE_TENANT_ID)"
terminal="$(repo_var TERMINAL_ENTRA_CLIENT_ID)"
pocket="$(repo_var POCKET_ENTRA_CLIENT_ID)"
workbench_app="$(az ad app list --filter "identifierUris/any(u:u eq 'api://tradingcenter-agent')" --query '[0].appId' -o tsv | tr -d '\r')"
gateway_app="$(az ad app list --filter "identifierUris/any(u:u eq 'api://tradingcenter-capital-gateway')" --query '[0].appId' -o tsv | tr -d '\r')"
for v in tenant terminal pocket workbench_app gateway_app; do
  [ -n "${!v}" ] || { echo "could not find $v" >&2; exit 1; }
done

set_variable ENTRA_TENANT_ID "$tenant"
set_variable TERMINAL_ENTRA_CLIENT_ID "$terminal"
set_variable POCKET_ENTRA_CLIENT_ID "$pocket"
set_variable TERMINAL_APPLICATION_ID "$terminal"
set_variable POCKET_APPLICATION_ID "$pocket"
# Both spellings of each API: a v1 token carries the identifier URI, a v2 token the application's client id.
set_variable WORKBENCH_ENTRA_AUDIENCES "api://tradingcenter-agent,$workbench_app"
set_variable GATEWAY_ENTRA_AUDIENCES "api://tradingcenter-capital-gateway,$gateway_app"

set_variable API_HOST "api.$DOMAIN"
set_variable GATEWAY_HOST "gateway.$DOMAIN"
set_variable TERMINAL_HOST "terminal.$DOMAIN"
set_variable POCKET_HOST "pocket.$DOMAIN"
set_variable ACME_EMAIL "$(repo_var TF_VAR_OPERATOR_EMAIL)"
set_variable IMAGE_PREFIX "ghcr.io/$REPO_LC"
set_variable DEPLOY_HOST "$HOST"
# The host key as this machine sees it now. The one `.local/vps/known_hosts` pinned at the first connection is the same
# key — compare them if the network between here and the server is not one you trust.
set_variable DEPLOY_KNOWN_HOSTS "$(ssh-keyscan -t ed25519 "$HOST" 2>/dev/null)"

echo
echo "Done. Names to answer on: api.$DOMAIN gateway.$DOMAIN terminal.$DOMAIN pocket.$DOMAIN"
echo "Not set (optional): ALERT_BOT_TOKEN ALERT_CHAT_ID TELEGRAM_API_ID TELEGRAM_API_HASH TELEGRAM_SESSION_KEY"
echo "Owner of the images: $OWNER_LC"
