# Database load — method

## Contents
- The budget
- Cost classes
- Where load hides here
- Classifying one statement
- Evidence (tiers T1–T4)
- Calibration: the September incidents

## The budget

Read the numbers from `infra/` on every run; these held on 23 September 2026.

- `psql-tradingcenter`: `B_Standard_B1ms` — Burstable, one vCore, 2 GiB, 32 GB of storage. Below a
  baseline of about 20% of the vCore the server earns credits; above it, it spends them; with none
  left it is held at the baseline, and **all seven databases on it** slow down together.
- `max_connections` is 50 (measured); application pools are budgeted at 30 by
  `scripts/tests/test_pool_budget.py`, which still assumes 35.
- App Service plan `asp-tradingcenter`: B2, one worker. The workbench process holds six pools.

A usable target: what runs with nobody looking stays at a few percent of the vCore, so the
operator's own use and a backfill have the headroom. Credits that fall day after day mean sustained
load above the baseline, whatever any single hour looks like.

## Cost classes

Give every statement that runs on a timer — or behind a poll — one of these, then multiply by its
cadence and fan-out, and ask whether it runs with nobody looking.

| Class | Cost grows with | Examples | On a timer? |
|---|---|---|---|
| C0 | nothing | primary-key lookup; an index range with a small `LIMIT`; `SELECT 1` | fine |
| C1 | what arrived since the last tick | insert new candles; read rows after a watermark | fine |
| C2 | the working set the operator chose | one indexed read per tracked pair, event or watch | fine while the set is small — watch for N+1 |
| C3 | the depth of the archive | `count(*)` over a big table or a join, `min()`/`max()` no index serves, `DISTINCT` over history, a deep `OFFSET`, `DELETE`/`UPDATE` whose predicate no index serves, bookkeeping rescanned whole | **never** — on demand only, bounded and rare |

C3 on a timer is the shape of both September incidents. A C3 that only a person triggers — a
report, a deletion — is acceptable when bounded and rare, and still worth a note when a screen
polls it.

## Where load hides here

Listed by mechanism, because files move. `scan.json` has candidates for each; read them — the list
is a map, not a verdict.

1. **Loops started in a lifespan** — `asyncio.create_task` + `while True` + `asyncio.sleep`.
   Cadences live in each package's `config.py` (`*_interval_seconds`) or a module constant. On
   23 September: the market_data ingest supervisor and its reconcile (5 min), the job runner's idle
   poll (5 s per worker), the candle-age gauge refresh (60 s); the Polymarket sampler (60 s) and its
   catch-up; the social collector (300 s); strategy evaluation (60 s); the teams scheduler clock
   (15 s); the Telegram binding watcher. For each: what one tick reads, for how many items, and what
   it does when nothing is new.
2. **Gauges that compute by querying.** A metric refreshed by a loop or an observable callback runs
   forever, users or not — #264 was exactly this.
3. **Health routes.** `/health` is called by the App Service health check, the availability test in
   `infra/monitoring.tf`, `scripts/deploy_probe.py` and the terminal's `useSourceHealth` (15 s).
   Anything beyond `SELECT 1` behind it is a loop in disguise.
4. **Screen polls.** `POLL_MS` / `refetchInterval` in the terminal (TanStack Query; the shared hook
   is `src/data/query.ts`), `window.setInterval` hooks in the pocket. By default TanStack Query stops
   polling while the document is hidden (`refetchIntervalInBackground: false`), but a tab visible on
   a second monitor keeps polling, and a raw `setInterval` never stops by itself. For each poll:
   the route, and the SQL behind the route, classified.
5. **Reads through tools.** A scheduled team, or the strategy loop through
   `workbench/archive_client.py`, reads the archive in-process; a tool that summarises "everything"
   is C3 multiplied by every run. Check the window is bounded and served by
   `candles_pkey (symbol, resolution, period_start)` — and remember the in-process call still
   serialises JSON, which is the app's CPU rather than the database's.
6. **Bookkeeping tables** — coverage, collected ranges, job chunks, usage, tool calls, run steps,
   messages: tables that only grow. #263 was bookkeeping that never compacted, plus a per-tick
   statement over all of it.
7. **N+1.** A statement inside a `for` over pairs, events, outcomes or watches: C2 × round trips ×
   cadence. One set-based statement usually does it.
8. **Holding a connection.** A connection kept across an `await` on HTTP or a model call starves
   the pool; the symptom is the pool's own 503 after five seconds.
9. **Migrations on big tables.** They run at startup under the advisory lock. `CREATE INDEX` on
   `candles` without `CONCURRENTLY` blocks writes and burns CPU for as long as it takes; no
   migration here uses `CONCURRENTLY` today, so flag any new one that touches a big table.
10. **Retention.** For every growing table: is there a bound — a window, a rollup, a delete? No
    bound means every C3 gets slower forever and the 32 GB fills.

## Classifying one statement

1. Find the SQL — a module constant such as `_SELECT_STATUS`, or inline in `conn.fetch*` /
   `execute*` — and its caller chain up to the trigger: loop, gauge, route, tool or poll.
2. Cadence: interval × fan-out (per pair, per watch…). Idle: does it run when nobody looks and
   nothing is new?
3. Predicates against indexes: `scan.json → hotspots.indexes[table]`, then the migration itself
   (`modules/workbench/migrations/<chain>/versions/`, `modules/telegram-gateway/migrations/versions/`).
   A composite index serves a predicate on its leading columns only.
4. Class C0–C3, and rows touched at today's scale — from tier T2 or T4, or "unknown" plus how to
   measure it.
5. Verdict: keep · bound it · make it incremental · keep a counter by trigger (as #264 did) · move it
   off the timer · delete it.

## Evidence

State in the report which tiers you had. A C3 claim from reading alone is plausible, not
confirmed, until a plan shows it.

**T1 — reading the code.** Always.

**T2 — the dev database, only if it is already up** (`docker ps --filter name=tradingcenter-db`).
Never start it. `market_data` is the container's superuser and the socket inside trusts it, so no
password is needed:

```
docker exec tradingcenter-db psql -U market_data -d <database> -c "\l"
docker exec tradingcenter-db psql -U market_data -d <database> -c "EXPLAIN <statement, literals in place of \$1…>"
docker exec tradingcenter-db psql -U market_data -d <database> -c "SELECT relname, n_live_tup, seq_scan, seq_tup_read, idx_scan, pg_size_pretty(pg_total_relation_size(relid)) FROM pg_stat_user_tables ORDER BY pg_total_relation_size(relid) DESC LIMIT 15"
```

Dev holds less data than production, so a small table may honestly plan as a sequential scan;
`SET enable_seqscan = off;` before the `EXPLAIN` shows whether an index *could* serve the predicate.
No `EXPLAIN ANALYZE` on `candles` or another big table, and no writes.

**T3 — production metrics, read-only**, when `az account show` succeeds:

```
SRV=$(az postgres flexible-server show -g rg-tradingcenter -n psql-tradingcenter --query id -o tsv)
az monitor metrics list --resource "$SRV" --metrics cpu_credits_remaining cpu_percent active_connections storage_percent --interval PT1H --offset 14d --aggregation Minimum Average Maximum -o table
PLAN=$(az appservice plan show -g rg-tradingcenter -n asp-tradingcenter --query id -o tsv)
az monitor metrics list --resource "$PLAN" --metrics CpuPercentage MemoryPercentage --interval PT1H --offset 14d --aggregation Average Maximum -o table
```

Credits falling day over day mean sustained load above the baseline; flat near the ceiling is
healthy. The names come from `infra/`; re-read them there if these fail.

**T4 — production statistics, only on the operator's explicit yes in this conversation.** It needs
a temporary firewall rule for the operator's current IP and an Entra token; remove the rule before
the session ends. `pg_stat_user_tables` (`seq_scan`, `seq_tup_read`, `n_live_tup`) shows which
tables are scanned whole; `pg_stat_activity` shows what runs now. `pg_stat_statements` is preloaded
but not created (`azure.extensions` is empty) — enabling it is an infrastructure change, so it is a
proposal, never a step of the review.

## Calibration: the September incidents

Both were measured on production on 23 September 2026, a week after the credits ran out.

- **#264 · market_data pair status.** The status read behind the candle-age gauge, `GET /pairs` and
  the pairs tool grouped a join over every candle to count them: a full scan of `candles` each
  minute with nobody watching, and every 15 s while the terminal showed the grid — 48.4 s at 1.1 M
  rows on the throttled server. Fix: earliest and latest candle as primary-key probes (25.7 ms for
  all 29 pairs), and the count kept in `candle_counts` by statement-level triggers.
- **#263 · Polymarket collected ranges.** A tick covered the one interval before it, but the loop
  sleeps a whole interval after a pass, so consecutive ticks never touched and nothing merged:
  5.4 M ranges (~21 000 per outcome), and the merge read all of them on `(outcome_id, starts_at)` —
  47 s for one event. With the sampler's database concurrency equal to the pool size, every read
  waited out its five seconds and got a 503. Fix: a tick covers the time since the previous one, an
  index on `(outcome_id, ends_at)`, history reads asking for `min`/`max` instead of every range, and
  the sampler's share of the pool below its size. The old test ran two ticks back to back, which
  the loop never does.

Two lessons carry to every run. The symptom — 503s, slow screens, every database at once — came
days after the cause and far from it, so look for the *shape*, not the symptom. And a test that
does not space ticks the way the loop does cannot see bookkeeping grow: check that growing tables
stay bounded in fact (T2/T4 row counts), not only in design.
