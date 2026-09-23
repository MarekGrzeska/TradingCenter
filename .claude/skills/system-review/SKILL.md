---
name: system-review
description: Periodic whole-system review of TradingCenter — what runs and what it costs the database, what is more complicated than one operator needs, what makes the next LLM-written change expensive, and which skills should exist for work, tests and deploy — ending in a Polish HTML report in docs/ with a phased plan and a findings ledger the next review picks up. Use it whenever the user asks for a review, audit or przegląd of the whole system, codebase, architecture or project ("zrób przegląd", "przegląd całości", "audyt architektury", "co obciąża bazę", "co można uprościć", "okresowy przegląd", "/system-review"), or for one lens of it ("przegląd tylko bazy", "prostota pod LLM", "jakie skille dodać"). Not for a diff or a PR (code-review), a security pass over pending changes (security-review), or an incident happening right now — diagnose that directly.
argument-hint: "[full | db | arch | dx | skills]"
---

# System review

Run every few weeks, or after a burst of big merges. Three properties make it worth repeating
rather than a one-off essay, and every step below serves one of them:

- **Comparable.** One script measures the same things each time (`scripts/scan.py`), the same
  seven areas are read, and a ledger of findings with stable IDs travels inside the report for the
  next run to re-check.
- **Aimed at cost that grows with data.** That is what exhausted the database in September 2026,
  a week before anyone saw a symptom.
- **Judged for one operator.** A single user, a demo account, code written mostly by an LLM — not
  what a team or a bank would need.

## Lenses, in priority order

**1 · Cost follows use, not history.** On 16 September 2026 `psql-tradingcenter` (Burstable B1ms:
one vCore, a baseline of about 20% of it, the rest on credits) ran out of CPU credits, and every
database on the server slowed at once. Two statements cost in proportion to the archive's depth:
the pair status counted every candle through a join — every minute from a gauge with nobody
watching, every 15 s while the terminal showed the grid, 48.4 s at 1.1 M rows (#264) — and a
Polymarket range merge read all 5.4 M collected ranges, 47 s for one event (#263). The symptom, 503
"no database connection came free within 5s" and slow screens, arrived far from both. The
operator's constraint is explicit: **fix the load, don't buy a bigger server.** So every loop,
gauge, health check and screen poll gets a cadence and a cost class. Method:
`references/db-load.md`.

**2 · As simple as one operator needs.** Every process, database, auth layer, setting, CI job,
document and spec has to pay for itself for one person on a demo account. A guard against a threat
that does not exist here is a cost. A guard where a miss means silent archive corruption, a second
position, real money or a leaked secret is not — CLAUDE.md lists those ("None of this touches…");
a proposal that weakens one says so and is never a quick win.

**3 · Cheap for an LLM to change.** Most code here is written by a model working from a limited
context. It gets cheaper when the always-loaded context is small (CLAUDE.md is paid in every
session; a skill costs its description until used), each thing has one obvious home, files are
small, one fast command verifies a change, procedures live in skills rather than prose, and
nothing stale pollutes search — leftover directories, nested worktrees, settings nobody reads.

**4 · Skills for the recurring work.** Inventory what exists; find the procedures that repeat in
git history, runbooks, memory notes and CLAUDE.md; propose skills for work, tests and deploy, each
naming what it lets CLAUDE.md drop. Later runs check which were built and whether they are used.
Method: `references/skills-catalogue.md`.

## Standing questions

Answer each on every run, with a number where one exists. The ledger stores them; the trend is
the point.

1. What does the database do while nobody is looking? (idle rows of the DB budget, by cost class)
2. What grows without a bound? (tables with no retention, docs, specs)
3. How much context must an LLM load before a safe change? (CLAUDE.md tokens plus the reads it requires)
4. How many moving parts? (processes, databases, Entra applications, settings, CI jobs, workflows)
5. Is each deployable still justified by a boundary that matters to one operator?
6. Is the process ceremony paying for itself? (OpenSpec changes and spec lines per month against code changed)
7. What is left over? (directories, worktrees, branches, settings)

## Guardrails

- **Read-only**, except the report and moving the previous report into `docs/archive/`. No code
  edits, commits or PRs unless the operator asks after reading.
- **The dev stack is the operator's.** Never start, stop or restart it. If the compose database
  (`tradingcenter-db`) is already up, read-only queries are fine — `EXPLAIN` (no `ANALYZE` on a big
  table), `pg_stat_*`, sizes.
- **Production is read-only and opt-in.** Azure Monitor metrics only when `az account show`
  succeeds. Reading the production database needs a temporary firewall rule: ask first, and remove
  it before the session ends.
- **No secret leaves its file.** A `.env`, a Terraform state or a plan file is reported by path,
  never by content.
- **No live tests** — `--run-live` and `--run-live-trading` never run here.

## Workflow

Scope comes from the arguments; `full` is the default. A focused run keeps steps 0, 2, 4 and the
ledger, and narrows step 1 — `db`: agents A, B, C, F · `arch` or `dx`: D, E, G · `skills`: G alone.

### 0 · Baseline — yourself, before any agent

1. **The previous review.** The newest `docs/przeglad-*.html`, else the newest in `docs/archive/`.
   If it carries a ledger (`<script type="application/json" id="review-ledger">`), load it. Reviews
   written before this skill have none: rebuild their open items from the proposals and plan
   sections. The previous commit is the ledger's `commit`, or the `main @ <sha>` in the header strip.
2. **Measure**, from the repository root (`<scratchpad>` is this session's scratchpad directory):
   ```
   python .claude/skills/system-review/scripts/scan.py --out <scratchpad>/scan.json --since <previous-commit> --previous <previous-report>
   uv run --no-project python scripts/measure-duplication.py --threshold 70
   ```
   `scan.py` is read-only and takes about ten seconds. It prints a summary and writes the metrics,
   the largest changes since the previous review, and hotspot candidates — loops, cadences, gauges,
   health routes, screen polls, every SQL statement with its risky constructs flagged, and the
   indexes per table read from the migrations. Every entry carries an `area`, so each agent gets
   its own slice. The summary is for you; the JSON is for the agents.
3. **The big changes.** The top of `since.largest`, plus anything flagged `adds_loop`, `adds_sql`,
   `adds_poll` or `migration`, is where load and complexity arrived. Each gets a one-line verdict in
   the report: did it earn its weight, and what does it cost at runtime?
4. **The budget, read from infra rather than remembered**: database SKU and storage
   (`infra/database.tf`), plan SKU (`infra/app-service.tf`), pool sizes
   (`scripts/tests/test_pool_budget.py`). The server's real `max_connections` is 50 (measured
   16 September 2026); that test assumes 35.
5. **Production signals**, if available — `references/db-load.md`, "Evidence". The report says
   which tiers you had.

### 1 · Fan out — seven agents in one message

Launch them together with the Agent tool (`general-purpose`), each with the common part and its
own brief from `references/agent-briefs.md`, plus: the `scan.json` path and its `area` keys, the
previous ledger's open items for the area, and the big changes whose `areas` touch it.

| Agent | Area | `area` keys in scan.json |
|---|---|---|
| A · candles | `modules/workbench/market_data` | `workbench/market_data` |
| B · archives | `polymarket_data`, `social_data` | `workbench/polymarket_data`, `workbench/social_data` |
| C · decisions | `strategy`, `teams`, `teams_tools` | `workbench/strategy`, `workbench/teams`, `workbench/teams_tools` |
| D · conversation | `agent`, `workbench/` (the assembly), `packages/tc-openai` | `workbench/agent`, `workbench/workbench`, `tc-openai` |
| E · edges | `capital-gateway`, `trading-mcp`, `telegram-gateway`, `packages/tc-runtime`, `packages/tc-mcp-kit` | the same names |
| F · screens | `terminal`, `pocket` — and the SQL behind every poll | `terminal`, `pocket` |
| G · process | CLAUDE.md, `docs/`, `openspec/`, `scripts/`, `.github/`, `infra/`, `.claude/`, tests, hygiene, skills | everything else, plus `metrics` |

The split follows the database: A, B and C own the tables and loops that grow, so each gets a
whole agent; F follows every poll down to its SQL, because a tab left open is a loop too. While
they run, lay out the DB budget skeleton from `scan.json`.

### 2 · Verify before you write

Agents over-report, and a wrong finding costs the operator a day in the wrong place — the
September review found three of its own claims false after acting on them. So:

- open the cited lines of every `high` finding and of every claim of class C3 yourself;
- for a database claim, find the index in the migration (`scan.json → hotspots.indexes`) and, if
  the dev database is up, `EXPLAIN` the statement;
- drop or downgrade what does not hold. The ledger says `verified: true` only for what you checked.

### 3 · Judge and plan

- **Scorecard** — one row per area: `ok` / `att` / `stop`, one line of why, the trend since the
  last review.
- **DB budget** — every loop, gauge, health check and screen poll: cadence, what it reads, cost
  class, whether it runs with nobody looking, verdict. This is the heart of the report: the
  operator should see at a glance what the database does while they sleep.
- **Proposals** — ID, what, why (finding IDs), the files it touches, effort S/M/L, risk, OpenSpec
  yes/no (CLAUDE.md's test: name the files), and a measurable exit ("`seq_tup_read` on X flat over
  a day", "CLAUDE.md under N characters", "N settings fewer"). Write each so that "rób P3" is a
  complete instruction.
- **Plan** in phases, cheapest risk-reduction first: 0 · quick wins (≤ 1 day each, no OpenSpec) ·
  1 · database load · 2 · simplification · 3 · skills. Every phase ends in a number.
- **What I do not propose** — rejected options, each with its reason. "A bigger database or plan"
  stays on that list unless the evidence shows load proportional to use that still exceeds the
  budget.

### 4 · Write the report

Structure, ledger schema and writing rules: `references/report.md`. In short: Polish prose,
English identifiers; a copy of `docs/style-template.html` (light only, its components,
`docs/style.md`); verdict first; tables and cards over narrative; every finding cites `path:line`;
about fifteen minutes of reading.

Save it as `docs/przeglad-YYYY-MM-DD.html`. Move the previous review into `docs/archive/` with
`git mv` — `docs/` says what is true today, the archive is the road — and name it as the
predecessor in the footer.

### 5 · Close

Answer in Polish, briefly: the verdict in three to five lines, the top three plan items, the
report's path, and what the run cost (agents and minutes, also written to the ledger's `run`).
Offer in one line to publish the report as a private Artifact and to open a branch and PR for it.
Do not start on the plan; the operator chooses what comes first.

## Files

| File | When |
|---|---|
| `references/db-load.md` | step 0.5 and step 2; agents A, B, C, E and F read it |
| `references/agent-briefs.md` | step 1 — the common part plus one brief per agent |
| `references/report.md` | step 4 |
| `references/skills-catalogue.md` | agent G; section 09 of the report |
| `scripts/scan.py` | step 0.2 — read-only; `--help` lists the options |
