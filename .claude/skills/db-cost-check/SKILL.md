---
name: db-cost-check
description: Before a SQL statement, a loop, a gauge, a health check or a screen poll lands in TradingCenter, price it — cost class C0–C3, how often it runs and for how many items, whether it runs with nobody looking — and prove the class with EXPLAIN on the dev database (or on a throwaway database with production-sized synthetic data). Use it while writing or reviewing anything that touches the database on a timer or per event ("nowe zapytanie", "dodaję pętlę", "polling co N sekund", "czy to obciąży bazę", "EXPLAIN", "db cost", "index for this query", "is this query cheap"), and when prod-health points at a statement. Not for a whole-system audit (system-review) and not for production statistics (prod-health).
---

# Database cost check

The database is one Burstable B1ms vCore shared by seven databases. Below ~20% of it the server
earns credits; above, it spends them; at zero **everything slows together**. Both September 2026
incidents were statements whose cost grew with the archive's depth, run on a timer: a pair status
that counted every candle every minute (#264), and a range merge that read 5.4 M rows per event
(#263). The steadiest load of all was a cheap check run after every stream message — 97% of the
server's transactions. None of it looked expensive in a diff.

## The five questions — answer each in the PR description

1. **What triggers it?** Follow the caller chain to a loop, gauge, route, tool or poll.
2. **How often, times how many?** Interval × fan-out (per pair, per event, per message). A
   per-message statement on a stream is the rate of the stream.
3. **Does it run with nobody looking?** Loops, gauges and health routes always do; a screen poll
   does while the tab is visible (hidden tabs should not poll).
4. **Which class?** C0 nothing · C1 what arrived since the last tick · C2 the working set the
   operator chose · C3 the depth of the archive. Definitions and examples:
   `.claude/skills/system-review/references/db-load.md`, "Cost classes". **C3 never on a timer.**
5. **What does the plan say?** Run the script below. A class claimed from reading alone is a guess.

## Prove it — `scripts/explain.sh`

```bash
bash .claude/skills/db-cost-check/scripts/explain.sh <database> "<SQL with literals for parameters>"
# databases: market_data agent teams polymarket social strategy telegram
```

It runs `EXPLAIN (ANALYZE, BUFFERS)` inside a rolled-back transaction on the **dev** database
(the running `tradingcenter-db` container — never started or restarted by this skill), then the
same plan with `enable_seqscan = off`. The second answers "*could* an index serve this?" when the
dev table is too small for the planner to bother. Read three things: the node that touches the
most rows, whether the predicate appears as `Index Cond` (served) or `Filter` (read, then thrown
away), and `Buffers: shared` — pages read is the cost that scales.

## When the dev data is too small to tell

Dev tables hold hundreds of rows where production holds millions, and the planner's choice at 300
rows says nothing about 5 M. Build the table at production scale in a **throwaway** container, not
in the dev database:

```bash
docker run -d --rm --name tc-cost-bench -e POSTGRES_PASSWORD=x -e POSTGRES_USER=b -e POSTGRES_DB=b \
  --cpus=1 --memory=2g postgres:16
# apply the chain: uv run python -c "from tc_runtime.migrate import upgrade_to_head ..." against it,
# fill with generate_series to today's row counts (prod-health or the latest review has them),
# ANALYZE, EXPLAIN (ANALYZE, BUFFERS) — then: docker stop tc-cost-bench
```

`--cpus=1 --memory=2g` approximates the B1ms; production disk is slower, so treat timings as a
floor. On 23 September 2026 this measured a 5.2 M-row migration at 4.1 s and a cost-limit sum at
353 buffers instead of 1,817 before either reached production.

## Verdicts

Keep · bound it (`LIMIT`, a date floor on an indexed column) · make it incremental (a watermark) ·
keep a counter maintained by trigger (#264) · move it off the timer · delete it. A new index is a
migration in the package's own chain, created under its lock at startup — on a big table say how
long the build holds it.

## Traps

- **A row the `WHERE` of `ON CONFLICT … DO UPDATE` skips is not returned by `RETURNING`** — read ids
  back separately (Polymarket's `upsert_event`).
- **A limit that protects money is not a place to trade correctness for speed** — a date floor on
  `runs.created_at` would undercount a run longer than the floor; index the column the sum filters on.
- **`count(*)` for a screen** is C3 however small today; keep a counter or show "at least N".
