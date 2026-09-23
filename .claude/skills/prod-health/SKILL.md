---
name: prod-health
description: Read-only health check of TradingCenter's production in Azure — do the three App Services answer, is any alert firing, how much CPU credit the B1ms database has left, how close the B2 plan is to its memory ceiling, what failed in the last hour — and, only with the operator's yes, which statements load the database. Use it when production seems silent, slow or wrong ("produkcja milczy", "coś zwolniło", "czy produkcja żyje", "co z bazą", "sprawdź produkcję", "prod health", "503 on the terminal", "alert przyszedł"), after a deploy looked odd, or before measuring anything. Not for a deploy in flight (deploy-watch) and not for fixing — it says where to look, then diagnose directly.
---

# Production health

The two incidents that shaped this: on 16 September 2026 the database ran out of CPU credits and
every screen slowed at once, a week after the cause landed; on 10 August an alert had been firing
for fifteen hours, so nobody read it during the outage. Symptoms arrive far from causes — so read
the whole board in the same order every time, cheapest and most telling first.

## 1 · The board — `scripts/health.sh`

```bash
bash .claude/skills/prod-health/scripts/health.sh
```

Read-only, about a minute, `az` logged in (`az account show`). It prints, in this order:

1. **Probes** — the three apps on their unauthenticated paths: workbench `/health`, gateway `/`,
   trading-mcp `/health`. Anything but 200 is the answer; stop and look at that app.
2. **Alerts firing now** — Azure Monitor, last day. A fired alert that has been firing for hours is
   itself a finding: it cannot tell anyone about the next thing.
3. **Database** — `cpu_credits_remaining` and `cpu_percent` per hour, 12 h. **Credits first**: the
   B1ms baseline is ~20% of one vCore; credits falling hour over hour mean sustained load above it,
   and at zero everything slows together. Then storage.
4. **Plan** — `MemoryPercentage` and `CpuPercentage` max per hour, 12 h. The alert is at 92%; the
   stage-4 decision was taken at 85%. A peak exactly in a deploy's hour is two containers overlapping.
5. **Availability tests** — last hour, per test (`success` is the string `"1"`, not a bool).
6. **Exceptions and errors** — last hour, per role, top messages.

## 2 · Reading it

| You see | It usually means | Next |
|---|---|---|
| a probe ≠ 200 | the container did not come up or crashed | `deploy-watch`'s rollback if a deploy just ran; else the app's log stream |
| credits falling, CPU > 20% | a statement or loop costs more than the baseline | step 3, then `db-cost-check` on the culprit |
| credits flat, screens slow | not the database | exceptions by role; plan memory |
| memory max ≥ 90% outside deploys | a working set grew | `AverageMemoryWorkingSet` per app, 14 days: climbing between restarts is a leak |
| an alert fired for hours | a threshold that cannot clear | fix the rule before trusting it |

## 3 · Which statements — only on the operator's explicit yes

```bash
bash .claude/skills/prod-health/scripts/top-statements.sh
```

Opens a temporary firewall rule for this machine's address, reads the top statements from
`pg_stat_statements` (by total time and by calls, with their database), and deletes the rule on
any exit. It needs Docker (the dev database container supplies `psql` as a client only). Ask
first, every time: it opens the production database to this machine, and the output contains SQL.
Confirm afterwards that `az postgres flexible-server firewall-rule list` shows no `tmp-` rule.

Deeper, per-table evidence (`pg_stat_user_tables` deltas over ten minutes) is the system review's
T4 script: `.claude/skills/system-review/scripts/t4.sh`.

## Traps

- **Git Bash rewrites `/subscriptions/...`** into a Windows path and `az -o tsv` ends lines with
  `\r`: the scripts export `MSYS_NO_PATHCONV=1` and strip `\r`. Keep that in any command you add.
- **KQL column names `first` and `last` are functions** — an `az monitor app-insights query` using
  them fails with a bare "invalid properties" 400.
- **Metrics lag** by a few minutes; a fix deployed ten minutes ago is not in the hourly averages yet.
- **Never restart the dev stack** to get `psql`; `docker exec` into the running container only.
