# Skills — inventory and proposals

## Why this section exists

CLAUDE.md is loaded into every session — about 23 000 characters, some 5 700 tokens, on
23 September 2026. A skill costs its name and description until it is used. So a procedure — how
to deploy, how to add a field to the archive, how to read production — is cheaper as a skill than
as a paragraph, and more reliable, because a skill can carry a script and its own guardrails.
CLAUDE.md keeps the map and the traps. Every skill proposal names the paragraphs it would let
CLAUDE.md drop; a proposal that drops nothing has to justify itself some other way.

## Inventory

- `.claude/skills/*/SKILL.md` and `.claude/commands/**` (`scan.json → metrics.claude`): name,
  purpose, last change (`git log -1 --format=%as -- <path>`). Flag overlap — the `opsx:*` commands
  and the `openspec-*` skills cover the same verbs.
- Evidence of use: mentions in commit messages or PR bodies, runbooks pointing at them, the operator
  saying so. "użycie nieznane" is an acceptable answer; a guess is not.

## Where candidates come from

1. CLAUDE.md paragraphs that describe a sequence of steps, or a trap to remember at a particular
   moment.
2. Runbooks in `docs/` — `kiedy-produkcja-milczy.html`, `rotacja-poswiadczen.html`,
   `dbeaver-azure-connection.html`, `git-worktree-praca-rownolegla.html`. A runbook read at two in
   the morning is a skill still missing its script.
3. Git history: fix-up commits that repeat (a contract regenerated, a CRLF artefact, a deploy-gate
   repair), and multi-step sequences that recur across PRs.
4. The operator's memory notes that encode a procedure: roll a failed container back before
   diagnosing it; check CPU credits first when anything is slow; an empty `git diff` beside an `M`
   in `git status` is line endings, not drift.
5. This review itself: every standing question that needed hand work is a script waiting to be
   written.

## What a good skill here looks like

- A trigger the operator would actually say, in Polish and in English.
- A procedure of at least three steps, or one trap; the deterministic parts as a script inside the
  skill; guardrails written as reasons rather than capitals.
- Small: `SKILL.md` under about 200 lines, details in `references/`.
- Proven by one real run before anyone relies on it.

## Built

`db-cost-check`, `contract-sync`, `deploy-watch`, `prod-health` — 23 September 2026 (P10 of that review),
each with one real run: prod-health's first board found the loop alert firing on restarts, contract-sync's
first run found its own CRLF blind spot. The next review marks each `used` or not from the evidence.

## Seed list — evaluate on every run, don't copy

**Work**
- `db-cost-check` — before a statement, loop, gauge or poll lands: classify it C0–C3, `EXPLAIN` it
  on the dev database, write its cadence down. This review's first lens as a five-minute habit; the
  September incidents are what it would have caught. The strongest candidate.
- `archive-field` — the five-stop route a new field travels through the archive's contract to both
  screens (`modules/workbench/market_data/README.md`), including `pnpm contract:generate` in the
  terminal and the pocket.
- `new-migration` — the right one of six alembic chains, ownership
  (`scripts/grant-schema-ownership.sql`), rules for big tables (lock time, `CONCURRENTLY`), a
  `-m db` test.
- `workbench-package` — a seventh package: the layering entry, the mount, the lifespan, the lock
  key, the caller record, the pool budget line, CI.

**Tests**
- `test-changed` — what CI's `changes` job would run, locally: from `git diff main...`, pick the
  modules, then `uv run pytest` · `ruff check .` · `pyright`, or `pnpm test` · `lint` ·
  `typecheck` · `contract:check`. `-m db` only when Docker is up; never live.
- `contract-sync` — regenerate every generated contract on both screens, recognise the CRLF artefact
  on Windows, run `contract:check`.

**Deploy and operations**
- `ship` — branch, tests for what changed, commit, PR. There is no branch protection here, so the
  skill waits for green checks itself.
- `deploy-watch` — after a merge: checks → `deploy-*.yml` (`workflow_run`) → `deploy_probe.py`. On a
  failed container start, roll the image back with `az` (about 40 s) before diagnosing.
- `prod-health` — read-only: app states, plan CPU and memory, database CPU credits, loop-liveness
  alerts; `pg_stat_*` only on the operator's yes, with the firewall rule removed afterwards.
  `kiedy-produkcja-milczy.html` and the credits note, as steps.
- `infra-plan` — `terraform plan`, a summary of the diff, a refusal of `azuread_*`, and the ordering
  trap (settings before the image that enforces them). `apply` stays the operator's.

**Meta**
- `system-review` — this skill. Its own line in the table: did the last run's findings hold
  (`false_findings`), and what did the run cost?

## In the report

`Nazwa | Rodzaj (praca / testy / deploy / operacje) | Kiedy się uruchamia | Co robi | Skrypty |
Co zdejmuje z CLAUDE.md | Priorytet (1–3) | Koszt`. From the second run on, add `Stan`: proposed ·
built (path) · used · retired.
