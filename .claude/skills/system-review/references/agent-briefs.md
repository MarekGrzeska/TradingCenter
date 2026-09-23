# Agent briefs

Each agent's prompt is three parts: the **common part** below, verbatim; its **area brief**; and the
run's specifics — the `scan.json` path with the agent's `area` keys, the previous ledger's open items
for the area, and the big changes whose `areas` touch it.

## Contents
- Common part (with the return format)
- A · candles · B · archives · C · decisions · D · conversation · E · edges · F · screens · G · process

## Common part

You are one of seven reviewers in a periodic whole-system review of TradingCenter — a monorepo run
by a single operator on a capital.com **demo** account, with code written mostly by an LLM. Read
`CLAUDE.md` first; it is the map.

Rules:
- Read-only. Do not edit files, start or stop services, run live tests or touch production. Never
  quote a secret: a `.env` is named by its path, never shown.
- Stay in your area. Follow a call chain out of it only when the cost lands in your area.
- Search with `git grep` / `git ls-files` or the Grep tool, never a bare `grep -r`: every module has
  a `.venv` with thousands of files, and `modules/` holds untracked leftovers from before the
  packages moved.
- `scan.json` lists candidates for your area — loops, cadences, gauges, health routes, screen polls,
  SQL statements with flags, indexes per table. Start there, then read the code: the list is a map,
  not findings.

Judge against four lenses, in this order:
1. **Cost follows use, not history.** If your area owns tables or a loop, or polls something that
   does, read `.claude/skills/system-review/references/db-load.md` first and classify every
   statement that runs on a timer or behind a poll (C0–C3).
2. **As simple as one operator needs.** What could be deleted, merged or made plainer, and what it
   would save — lines, files, settings, processes. The guards CLAUDE.md lists under "None of this
   touches…" stay; if a proposal weakens one, say so.
3. **Cheap for an LLM to change.** Large files; one thing kept in many places; a change that needs
   edits in N files; names that mislead; dead code; comments narrating history.
4. **Risks you trip over.** You are not hunting bugs, but write down a real one when you see it.

Evidence: every finding cites `path:line` and quotes at most two lines, or gives a measurement. No
evidence, no finding. Five strong findings beat twenty weak ones.

Return markdown only, in this shape:

```
### Findings
#### <AREA>-<n> · <the claim, at most 12 words>
- lens: db-load | simplicity | llm-dx | reliability | cost | hygiene
- severity: high | medium | low   (high = will hurt within weeks at today's growth, or taxes every change)
- evidence: `path:line` — "quote"   (or the measurement)
- mechanism: 1–3 sentences on why it costs what it costs. For db-load: trigger → cadence × fan-out → statement → class → rows at today's scale → runs idle yes/no
- fix: 1–3 sentences, the smallest change that removes the cost; the files it touches
- effort: S (< 2 h) | M (≤ 1 day) | L (more)
- protected: no | yes — which guard
- openspec: yes | no   (yes when it changes a requirement, a cross-module contract, infra, or a load-bearing rule)
- previous: the ledger id it continues, if any

### DB budget rows            (only if your area has any)
| trigger | cadence | reads | class | idle? | verdict |

### Previous items
<id> — done (commit) | partial | open | obsolete — evidence

### Big changes
<sha> <subject> — earned its weight? runtime cost? one line

### Could go
<what> — <lines / files / settings> — why nobody would miss it
```

## A · candles — `modules/workbench/market_data`

The largest table here, `candles`, and the loops that fill and watch it. Start with what `app.py`'s
lifespan starts, then `ingest/supervisor.py`, `jobs/runner.py` and `jobs/store.py`, `telemetry.py`,
`store.py`, `reads.py`, `rollups.py`, `coverage.py`, `tracking.py`, `routers/`.

- Every statement touching `candles` on a timer or behind a poll: a bounded range on
  `(symbol, resolution, period_start)`, or something that counts, aggregates or scans per tick?
- The job runner: how does an idle worker wait for work, how many workers, and what does one idle
  poll cost?
- Rollups (`derived_candles`) and coverage: incremental from the newest rows, or recomputed over
  history? Who triggers a refresh, and how often?
- Indicators: computed per request over how many candles, and how often do the screens ask?
- After #264: `_SELECT_STATUS` and the `candle_counts` triggers — still consistent, and what do the
  statement-level triggers cost on the write path of the ingest?
- The WebSocket hub: does a subscriber cost the database anything?

## B · archives — `polymarket_data`, `social_data`

Two collectors on a timer, and their bookkeeping.

- The Polymarket sampler (60 s): statements per tick per tracked outcome — one set-based write or
  N+1? After #263, do `collected_ranges` stay small in practice (row count per outcome)?
- Backfill and catch-up: bounded? What does each concurrent unit hold — connections, CPU? Does
  anything keep a connection across an HTTP call?
- `price_samples` and the other growing tables: rows per day, retention, and the reads the screens
  poll (terminal 30 s, pocket 60 s).
- The social collector (300 s): how it decides what is new; the model call per post — its money
  cost, and whether a failure makes it re-read everything.
- Groups (#265) and alert markers: indexed lookups, or scans?

## C · decisions — `strategy`, `teams`, `teams_tools`

Two loops that run with nobody looking and can multiply reads through tools.

- Strategy evaluation (60 s) × active watches: how many candles per evaluation through
  `workbench/archive_client.py`, over what window? The `decisions` table's growth; who counts it and
  how often?
- The teams scheduler clock (15 s): what one tick queries when nothing is due, and whether it calls
  tool servers on every tick. The indexes on `schedules.next_fire_at` / `triggers.next_check_at` —
  used by the actual predicates?
- Scheduled team runs: which tools they call, and whether one reads a whole history (C3 × runs per
  day). Cost-limit and usage sums: bounded by an index on day or owner?
- `teams/store/*` — memories, runs, steps, trades, usage, tool calls: growth and retention.

## D · conversation — `agent`, `workbench/`, `packages/tc-openai`

- Conversation storage — sessions, messages, tool calls, usage: growth, retention, and the reads
  behind the session list and the usage views (the `_USAGE_*` statements aggregate without a
  `WHERE` — over how many rows, and how often?).
- The assembly: six lifespans, six pools, six migration chains at startup — startup time, lock
  waits, and what adding a seventh package costs (count the places a new package must be named).
- The settings surface: what `workbench/config.py` reads, the doubled `AGENT_`/`TEAMS_` settings,
  settings nobody reads.
- `tests/test_layering.py`: what it costs a change, and what it has prevented.
- `tc-openai`: one file, one consumer — is being a package still worth it?

## E · edges — `capital-gateway`, `trading-mcp`, `telegram-gateway`, `packages/tc-runtime`, `packages/tc-mcp-kit`

- What each process costs to exist — App Service, identity, Easy Auth, CI job, deploy workflow,
  database — against the boundary it holds, for one operator. `trading-mcp`'s demo guard and write
  path are protected: say what a fold would change, not whether the guard matters.
- `telegram-gateway`: a database and a migration chain of its own for sending notifications — what
  it stores, what reads it how often (the binding watcher), and whether stage 4 of
  `one-process-per-security-boundary` (folding it into the workbench) is worth doing now.
- `tc_runtime`: pool defaults and acquire timeout, `liveness`, `caller_access`, migrations under the
  advisory lock — does anything there query on a timer?
- Health routes in every app: what each does, and who calls it how often — the App Service health
  check, `infra/monitoring.tf`, `scripts/deploy_probe.py`, the terminal.
- `capital-gateway`'s rate gate and stream hub: CPU only? Does anything wake when nobody is
  subscribed?

## F · screens — `modules/terminal`, `modules/pocket`

Every poll is a loop that lives as long as a tab is open.

- Every poll (`POLL_MS`, `refetchInterval`, `setInterval`): cadence, route, whether it pauses when
  the tab is hidden, and **the SQL behind the route** — follow it into the workbench and classify it
  C0–C3. This inventory is your main deliverable; return it as DB budget rows.
- What each screen fires when it opens; the same data requested twice; anything polled that could
  be pushed — the WebSocket already exists for candles.
- Size and shape: the largest components, logic duplicated between terminal and pocket, the
  generated contracts' size and churn.
- Tests against CLAUDE.md's "How much test is enough": sort order through the DOM, "the text
  appears", implementation details.

## G · process — CLAUDE.md, `docs/`, `openspec/`, `scripts/`, `.github/`, `infra/`, `.claude/`, tests, hygiene

The cost of changing anything, and what could go. `scan.json → metrics` has most of the numbers.

- CLAUDE.md against `scripts/tests/test_guide_ceiling.py`: which paragraphs are procedures (→
  skills), which are history (→ `docs/`), and what an LLM must read before a safe change.
- `docs/`: pages describing today against pages describing the road; stale pages; reading cost.
- `openspec/`: specs, active changes, changes archived in the last 30 days (`git log --since`), spec
  lines per change against the code lines it changed. Is the ceremony paying for itself for one
  operator, and what lighter form would keep what it gives?
- Tests: lines against production, the share of `-m db`, suites that break CLAUDE.md's test rules.
- CI and deploy: jobs per PR, the `changes` filter, the deploy workflows around
  `_deploy-app-service.yml`, `deploy_gate.py` and `deploy_probe.py` — what could be one workflow.
- Infra: resources by type, Easy Auth registrations, identities, alerts, monthly cost drivers — and
  what a single operator does not need.
- Settings: keys per `.env.example`, and every place a new setting must be declared (`config.py`,
  `.env.example`, `infra/app-service.tf`, the pool test…).
- Hygiene, from `metrics.hygiene`: leftover module directories (paths only; say whether one holds a
  `.env`), worktrees (nested ones pollute search), stale branches.
- Skills: the inventory and proposals per `references/skills-catalogue.md`. Return the skills table
  as well as the common format.
