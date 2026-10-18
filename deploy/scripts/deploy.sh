#!/bin/sh
# The one command the deploy key may run (`command="..."` in authorized_keys). The client says what it wants in
# SSH_ORIGINAL_COMMAND — one of the verbs below, with arguments that are checked here and never handed to a shell — and
# sends files on stdin. Nothing else is reachable with that key, whatever it asks for.
#
#   env                  .env on stdin: every name in env.required present and non-empty, or nothing is written
#   sync                 a tar of the compose file, Caddyfile, bootstrap script and env.required on stdin
#   www <terminal|pocket> a tar of a built front end on stdin, swapped in whole
#   login <user>         a registry token on stdin, for the pull of this release; logout removes it again
#   release <sha>        pull this commit's images and start them; on failure put the previous ones back and exit 1
#   rollback             put the previous images back
#   status               which images run, and whether they are healthy
set -eu
umask 027

APP_DIR="${APP_DIR:-/opt/tradingcenter}"
cd "$APP_DIR"

# Not `tradingcenter`, which is the name of the developer machine's `compose.yaml`: `--remove-orphans` below would take its database for one.
PROJECT="${COMPOSE_PROJECT:-tradingcenter-vps}"
COMPOSE="docker compose --project-name $PROJECT --env-file .env --env-file tags.env -f docker-compose.yml"
SERVICES="gateway trading-mcp workbench"
# How long a deploy waits for the new containers to be healthy. The workbench's first start migrates every database, and
# the candle archive's index can outlast a start-up — the compose file's own grace period is 1500 s.
HEALTH_WAIT_SECONDS="${HEALTH_WAIT_SECONDS:-1700}"

read -r verb arg extra <<EOF_CMD
${SSH_ORIGINAL_COMMAND:-${1:-}} ${2:-}
EOF_CMD
: "${verb:?no command given}"

die() { echo "deploy: $*" >&2; exit 1; }

# A commit id, a front-end name — nothing a shell or a path could make something of.
case "$arg" in
  *[!A-Za-z0-9._-]*) die "refused argument" ;;
esac

write_env() {
  new="$(mktemp .env.XXXXXX)"
  cat > "$new"
  missing=""
  for name in $(grep -v '^[[:space:]]*#' env.required | grep -v '^[[:space:]]*$'); do
    # An assignment with something after the equals sign; the value itself is never printed.
    if ! grep -Eq "^${name}=.+" "$new"; then
      missing="$missing $name"
    fi
  done
  if [ -n "$missing" ]; then
    rm -f "$new"
    die "refusing to deploy; missing from .env:$missing"
  fi
  chmod 600 "$new"
  mv "$new" .env
  echo "env: written"
}

sync_files() {
  tmp="$(mktemp -d)"
  tar -x -C "$tmp" -f -
  for f in docker-compose.yml Caddyfile env.required postgres/ensure-databases.sh; do
    [ -f "$tmp/$f" ] || { rm -rf "$tmp"; die "sync: $f is not in the archive"; }
  done
  cp "$tmp/docker-compose.yml" "$tmp/Caddyfile" "$tmp/env.required" .
  cp "$tmp/postgres/ensure-databases.sh" postgres/ensure-databases.sh
  rm -rf "$tmp"
  echo "sync: done"
}

swap_www() {
  case "$arg" in terminal|pocket) ;; *) die "www: terminal or pocket" ;; esac
  incoming="www/.${arg}.incoming"
  rm -rf "$incoming"; mkdir -p "$incoming"
  tar -x -C "$incoming" -f -
  [ -f "$incoming/index.html" ] || { rm -rf "$incoming"; die "www: no index.html in the archive"; }
  rm -rf "www/.${arg}.old"
  [ -d "www/$arg" ] && mv "www/$arg" "www/.${arg}.old"
  mv "$incoming" "www/$arg"
  rm -rf "www/.${arg}.old"
  echo "www: $arg swapped"
}


wait_healthy() {
  deadline=$(( $(date +%s) + HEALTH_WAIT_SECONDS ))
  while :; do
    pending=""
    for svc in $SERVICES; do
      id="$($COMPOSE ps -q "$svc")"
      state="$( [ -n "$id" ] && docker inspect -f '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}}' "$id" || echo missing)"
      case "$state" in
        "running healthy") ;;
        # A crash loop reads `restarting` between attempts; waiting out the deadline on it would only delay the rollback.
        "exited "*|"dead "*|"restarting "*|missing) echo "$svc: $state"; return 1 ;;
        *) pending="$pending $svc" ;;
      esac
    done
    [ -z "$pending" ] && return 0
    [ "$(date +%s)" -ge "$deadline" ] && { echo "still not healthy:$pending"; return 1; }
    sleep 5
  done
}

running_images() {
  for svc in $SERVICES; do
    id="$($COMPOSE ps -q "$svc")"
    [ -n "$id" ] && echo "$svc $(docker inspect -f '{{.Config.Image}}' "$id")"
  done
}

release() {
  sha="${arg:?release <sha>}"
  [ -f tags.env ] && cp tags.env tags.env.prev || : > tags.env.prev
  printf 'GATEWAY_TAG=%s\nTRADING_MCP_TAG=%s\nWORKBENCH_TAG=%s\n' "$sha" "$sha" "$sha" > tags.env
  $COMPOSE pull --quiet gateway trading-mcp workbench || { cp tags.env.prev tags.env; die "pull failed; nothing changed"; }
  $COMPOSE up -d --remove-orphans
  # The Caddyfile is a bind mount that `sync` rewrote in place; Caddy reads it only when told. A refused config keeps the old.
  if $COMPOSE exec -T caddy caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null 2>&1; then
    echo "caddy: reloaded"
  else
    echo "caddy: reload refused, the previous configuration stays"
  fi
  if wait_healthy; then
    echo "release: $sha is up"
    running_images
    return 0
  fi
  echo "release: $sha did not become healthy; putting the previous images back" >&2
  rollback_to_previous
  die "release $sha failed and was rolled back"
}

rollback_to_previous() {
  if [ -s tags.env.prev ]; then
    cp tags.env.prev tags.env
    $COMPOSE up -d --remove-orphans
    wait_healthy || echo "rollback: the previous images are not healthy either" >&2
  else
    echo "rollback: no previous release recorded; stopping the applications" >&2
    $COMPOSE stop workbench trading-mcp gateway
  fi
}

case "$verb" in
  login) [ -n "$arg" ] || die "login <user>"; docker login ghcr.io -u "$arg" --password-stdin >/dev/null && echo "login: ok" ;;
  logout) docker logout ghcr.io >/dev/null 2>&1 || true; echo "logout: done" ;;
  env) write_env ;;
  sync) sync_files ;;
  www) swap_www ;;
  release) release ;;
  rollback) rollback_to_previous ;;
  status) running_images; $COMPOSE ps ;;
  *) die "unknown command" ;;
esac
