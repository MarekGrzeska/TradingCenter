#!/usr/bin/env bash
# The production board, read-only: probes, firing alerts, database credits, plan memory, availability, errors.
#
#   bash .claude/skills/prod-health/scripts/health.sh [hours=12]
set -uo pipefail
# Git Bash rewrites an argument starting with /subscriptions/ into a Windows path without this.
export MSYS_NO_PATHCONV=1

HOURS="${1:-12}"
RG=rg-tradingcenter
APPI=appi-tradingcenter

tsv() { tr -d '\r'; }

kql() {
  az monitor app-insights query -g "$RG" --app "$APPI" --analytics-query "$1" --offset 1h -o json 2>/dev/null |
    python -c "import json,sys
try:
    rows = json.load(sys.stdin)['tables'][0]['rows']
except Exception:
    print('  (query failed)'); sys.exit()
for r in rows: print('  ' + '  '.join(str(c) for c in r))
if not rows: print('  (none)')"
}

metrics() {  # resource-id, metric, aggregation
  az monitor metrics list --resource "$1" --metrics "$2" --interval PT1H --offset "${HOURS}h" \
    --aggregation "$3" -o tsv --query "value[0].timeseries[0].data[].[timeStamp, $4]" 2>/dev/null | tsv |
    awk '{ printf "  %s %6.1f\n", substr($1, 6, 11), $2 }'
}

echo "== probes"
for url in https://app-tradingcenter-agent.azurewebsites.net/health \
           https://app-tradingcenter-gateway.azurewebsites.net/ \
           https://app-tradingcenter-trading-mcp.azurewebsites.net/health; do
  printf '  %s  %s\n' "$(curl -s -o /dev/null -w '%{http_code}' --max-time 60 "$url")" "$url"
done

echo "== alerts firing (last day)"
SUB=$(az account show --query id -o tsv | tsv)
az rest --method get \
  --url "https://management.azure.com/subscriptions/$SUB/providers/Microsoft.AlertsManagement/alerts?api-version=2019-05-05-preview&monitorCondition=Fired&timeRange=1d" \
  --query "value[].[properties.essentials.startDateTime, name]" -o tsv 2>/dev/null | tsv | sed 's/^/  /' |
  grep . || echo "  (none)"

SRV=$(az postgres flexible-server show -g "$RG" -n psql-tradingcenter --query id -o tsv | tsv)
echo "== database · CPU credits remaining (min per hour) — the first number to read"
metrics "$SRV" cpu_credits_remaining Minimum minimum
echo "== database · CPU % (avg per hour; baseline ≈ 20)"
metrics "$SRV" cpu_percent Average average
echo "== database · storage % (max, last hour)"
metrics "$SRV" storage_percent Maximum maximum | tail -1

PLAN=$(az appservice plan show -g "$RG" -n asp-tradingcenter --query id -o tsv | tsv)
echo "== plan · memory % (max per hour; alert 92, stage-4 line 85)"
metrics "$PLAN" MemoryPercentage Maximum maximum
echo "== plan · CPU % (max per hour)"
metrics "$PLAN" CpuPercentage Maximum maximum | tail -4

echo "== availability tests, last hour (success is the string '1')"
kql "availabilityResults | where timestamp > ago(1h) | summarize runs=count(), passed=countif(success == '1') by name"

echo "== exceptions, last hour"
kql "exceptions | where timestamp > ago(1h) | summarize n=count() by cloud_RoleName, type | top 8 by n"

echo "== error traces, last hour"
kql "traces | where timestamp > ago(1h) and severityLevel >= 3 | summarize n=count() by cloud_RoleName, msg=substring(message, 0, 110) | top 8 by n"
