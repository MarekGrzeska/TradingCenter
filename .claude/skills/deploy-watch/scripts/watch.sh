#!/usr/bin/env bash
# Follow one commit from checks to serving: the checks run, every deploy it triggered, the probes, and a rollback
# command for any app that is not answering.
#
#   bash .claude/skills/deploy-watch/scripts/watch.sh [sha=origin/main]
set -uo pipefail
export MSYS_NO_PATHCONV=1

RG=rg-tradingcenter
declare -A APPS=(
  [workbench]=app-tradingcenter-agent
  [capital-gateway]=app-tradingcenter-gateway
  [trading-mcp]=app-tradingcenter-trading-mcp
)
declare -A WORKFLOW=(
  [workbench]=deploy-workbench.yml
  [capital-gateway]=deploy-gateway.yml
  [trading-mcp]=deploy-trading-mcp.yml
)
declare -A HEALTH=(
  [workbench]=/health
  [capital-gateway]=/
  [trading-mcp]=/health
)

git fetch -q origin
SHA=$(git rev-parse "${1:-origin/main}")
echo "== commit ${SHA:0:12}  $(git log -1 --format=%s "$SHA")"

declare -A BEFORE
echo "== images serving now — the rollback targets"
for module in "${!APPS[@]}"; do
  BEFORE[$module]=$(az webapp show -g "$RG" -n "${APPS[$module]}" --query siteConfig.linuxFxVersion -o tsv | tr -d '\r')
  echo "  $module  ${BEFORE[$module]#DOCKER|}"
done

run_for() {  # workflow file -> "status conclusion url" of its run for SHA, or nothing
  gh run list --workflow "$1" --limit 20 --json headSha,status,conclusion,url \
    -q ".[] | select(.headSha == \"$SHA\") | \"\(.status) \(.conclusion) \(.url)\"" | head -1
}

echo "== checks"
until run=$(run_for checks.yml); [[ "$run" == completed* ]]; do sleep 20; done
echo "  $run"
[[ "$run" == "completed success"* ]] || { echo "checks did not pass — nothing will deploy"; exit 1; }

echo "== deploys (each starts only after the green checks run)"
sleep 30  # workflow_run needs a moment to be created
workflows=$(ls .github/workflows/deploy-*.yml | xargs -n1 basename)
for wf in $workflows; do
  until run=$(run_for "$wf"); [[ -z "$run" || "$run" == completed* ]]; do sleep 20; done
  echo "  $wf  ${run:-no run for this commit}"
done

echo "== probes"
for module in "${!APPS[@]}"; do
  app=${APPS[$module]}
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 90 "https://$app.azurewebsites.net${HEALTH[$module]}")
  now=$(az webapp show -g "$RG" -n "$app" --query siteConfig.linuxFxVersion -o tsv | tr -d '\r')
  moved=$([[ "$now" == "${BEFORE[$module]}" ]] && echo "unchanged" || echo "now ${now#DOCKER|}")
  echo "  $code  $module  ($moved)"
  if [[ "$code" != 200 ]]; then
    if [[ "$now" != "${BEFORE[$module]}" ]]; then
      echo "  ROLL BACK FIRST, diagnose after:"
      echo "    az webapp config container set -g $RG -n $app --container-image-name ${BEFORE[$module]#DOCKER|}"
    else
      echo "  the image did not change here; the previous tag is the headSha of the last successful"
      echo "  run of ${WORKFLOW[$module]} before this one: gh run list --workflow ${WORKFLOW[$module]}"
    fi
  fi
done
