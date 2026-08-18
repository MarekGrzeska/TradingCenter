# CLAUDE.md

Orientation for an agent working in this repo. `README.md` is the fuller narrative; this
file is the map and the things that will bite you if you assume the usual defaults.

## What this is

A monorepo of **independent** modules supporting trading and research. Every module runs
standalone — its own entrypoint, dependencies, tests and README — and modules cooperate
only through a published contract (HTTP/OpenAPI or typed events).

**No module imports another module.** That is the load-bearing rule and it has not moved:
at runtime a module reaches another only through a published contract, never through its
package, its database or its identity.

**Source may be shared at build time, through `packages/`, under three conditions** —
measured as a copy (≥70% identical), every difference expressible as an argument, and
every consumer's tests running on every change to the package. `docs/architecture.md`,
"What may be shared, and what may not", carries the rule and the measurement that changed
it on 18 August 2026. A package is resolved into each module's own lock and baked into
each module's own image; nothing is published or versioned. If a change seems to need
something a package cannot give it, the change is wrong, not the rule.

```
modules/capital-gateway   Python · capital.com: trading, history, live stream. Demo only.
modules/market-data       Python · the candle archive and its own indicators. Owns the PostgreSQL. Depends on the gateway.
modules/market-mcp        Python · MCP tools over market-data, reduced for a model. Read-only — no tool writes. Depends on market-data.
modules/agent             Python · the operator's conversation with a model. Own database, own OpenAI key. Reads the archive through market-mcp's tools, builds teams through teams-mcp's, and moves the demo account through trading-mcp's.
modules/teams             Python · teams of agents as data — a graph the operator composes, revisions, runs and their cost. Own database, own OpenAI key. Same market-mcp and trading-mcp tools as agent; no edge to agent itself.
modules/trading-mcp       Python · MCP tools over the gateway's demo account: positions, balance, orders. Network transport only, two named callers (teams, agent). Demo checked against the gateway, not against a setting.
modules/teams-mcp         Python · MCP tools over teams' catalogue, so the agent can build and correct a team by talking. One named caller (agent). Every tool acts in the operator's name — their token travels with the call, in its own header.
modules/terminal          React+TS · the operator's screen. Consumes the gateway, market-data, agent and teams. Publishes nothing.
packages/tc-runtime       Python · the plumbing measured as a hand-copy across modules: database, migrations, schema check, caller identity. A build-time dependency, never a runtime one; its README names the consumers.
infra/                    Terraform · Azure. `infra/bootstrap/` is a separate root with local state.
openspec/                 specs (the truth) + change proposals
docs/                     architecture and reference — only what is true today
docs/archive/             research from before a decision; the road, not the state
```

`terminal` is a consumer, not a peer — nothing depends on it. Call it the **terminal**,
never a "console" or "dashboard".

## Commands

Run these from the module directory. Nothing at the repo root builds or tests everything.

| Module | Commands |
|---|---|
| `capital-gateway` | `uv run uvicorn capital_gateway.app:app --reload --port 8010`<br>`uv run pytest` · `uv run ruff check .` · `uv run pyright` |
| `market-data` | `uv run alembic upgrade head` then `uv run uvicorn market_data.app:app --reload --port 8020`<br>`uv run pytest` · `uv run ruff check .` · `uv run pyright` |
| `market-mcp` | `uv run python -m market_mcp stdio` (desktop client) or `... http` (port 8040)<br>`uv run pytest` · `uv run ruff check .` · `uv run pyright` · `uv run python scripts/contract.py check` |
| `agent` | `uv run alembic upgrade head` then `uv run uvicorn agent.app:app --reload --port 8030`<br>`uv run pytest` · `uv run ruff check .` · `uv run pyright` |
| `packages/tc-runtime` | no entrypoint — a library<br>`uv run pytest` · `uv run ruff check .` · `uv run pyright` |
| `teams` | `uv run alembic upgrade head` then `uv run uvicorn teams.app:app --reload --port 8050`<br>`uv run pytest` · `uv run ruff check .` · `uv run pyright` |
| `trading-mcp` | `uv run python -m trading_mcp` (port 8060 — one transport, no `stdio` to choose)<br>`uv run pytest` · `uv run ruff check .` · `uv run pyright` · `uv run python scripts/contract.py check` |
| `teams-mcp` | `uv run python -m teams_mcp` (port 8070 — same, one transport)<br>`uv run pytest` · `uv run ruff check .` · `uv run pyright` · `uv run python scripts/contract.py check` |
| `terminal` | `pnpm dev` · `pnpm test` · `pnpm lint` · `pnpm typecheck` · `pnpm contract:check` |

Test flags that matter:

- `uv run pytest` alone runs unit tests; anything needing a database **skips** without Docker.
- `uv run pytest -m db` — integration tests against a throwaway PostgreSQL container
  (testcontainers, random port — safe to run in parallel). CI runs these.
- `uv run pytest -m live --run-live` — needs a real Capital demo session. **Never run in
  CI**, and see the session warning below.
- `--run-live-trading` (gateway only) **writes**: it opens, amends and closes demo positions.

The whole stack: `./scripts/dev.sh` on macOS and Linux, `./scripts/dev.ps1` on Windows —
the same script twice (`--no-terminal` / `-NoTerminal` for back end only). It starts things
in dependency order — migrations → gateway → market-data → market-mcp → trading-mcp →
teams → teams-mcp → agent → terminal — waiting for each to actually answer. Ports are
fixed: **8010** gateway, **8020** market-data, **8030** agent, **8040** market-mcp,
**8050** teams, **8060** trading-mcp, **8070** teams-mcp, **5173** terminal.

`trading-mcp` is the one module that will not start on a wish: `CAPITAL_GATEWAY_API_KEY` in
its `.env` must be the gateway's own `GATEWAY_API_KEY` (the gateway checks the header on
loopback too), and it asks the gateway whether the account is a demo one *before* it opens
a port. Both dev scripts compare the two files and refuse up front, because otherwise the
symptom is the whole stack going down with "a service exited".

## Things that will bite you

**The dev database is the compose.yaml container.** `market-data` writes to a local
PostgreSQL on `127.0.0.1:55432`, which the dev scripts start first — Docker is required to
run the stack, not only to test it. Leaving `DATABASE_USER` unset is what selects this
local mode, and it narrows the module to loopback: a `DATABASE_URL` pointing at any remote
host (production included) is refused at startup, by `dev.sh` and by `config.py` both.
Production connects with an Entra identity instead — `DATABASE_USER` set in
`infra/app-service.tf` — and that path is not for local use. (Do not "restore" the brief
arrangement where dev ran on the Azure server; it was reversed the same day it was made —
`openspec/changes/local-dev-database-in-docker`.)

`agent` and `teams` write to further logical databases (`agent`, `teams`) in the same
container, on the same port — one Postgres server, three schemas, the same shape as
production's own `psql-tradingcenter` (`infra/database.tf`). The dev scripts create each
role and database themselves if either is missing, since `docker-entrypoint-initdb.d` only
ever runs against an empty volume and would never fire for a `tradingcenter-db-data` from
before those modules existed.

**The terminal's contract is generated.** `src/data/contract.generated.ts` is built from the
schema `market-data` derives from its own models. After changing anything in
`market_data/contract.py`, run `pnpm contract:generate` in the terminal — CI's
`contract:check` fails on a stale file, and it runs before the terminal's tests on purpose.
The whole route a new field travels is below, under "A new field on market-data's wire".

**Capital sessions coexist — the old warning here was never measured, and it was wrong.**
This file used to say that capital.com invalidates the previous session on every new login,
so two gateway processes deauthenticate each other. Measured against the demo API on
10 August 2026, all of it with `GET /accounts` proving each session usable, not merely
present:

- four sessions opened with **one** API key: all four still answered after the fourth
  login, and still answered a minute later. No eviction, no cap at four, no delay;
- two sessions from **two** API keys under one login: both answered, in either order;
- two streaming connections on one account subscribed to the same epic: both kept
  receiving quotes, whether the sessions came from one key or two.

An API key carries **its own password**, set when the key is created — not the account's
login password. A second key with the first key's password answers
`401 {"errorCode":"error.invalid.details"}`, which reads exactly like an invalidated
session and is not one.

What still constrains parallel work is the rate budget, not the session: capital.com counts
its 10 requests/second against the **account**, so two stacks share one allowance and starve
each other. Together with the fixed ports and the single dev database container, that is
still a reason to run one stack at a time — a different reason, with a different symptom
(slowness, not 401s). Not measured: live accounts, and whether this behaviour is stable
over time. A 401 storm was really observed on 9–10 August; `stream_tokens_for` in
`capital_gateway/app.py` names what does explain it, which is a session going idle.

**Env files are per-module and gitignored.** Copy from `.env.example`. The gateway needs
`CAPITAL_*` demo credentials plus its own `GATEWAY_API_KEY`; market-data needs the same
`GATEWAY_API_KEY`, a `DATABASE_URL` and the `AZURE_*` identity it connects to Postgres with.
market-mcp needs no `.env` at all locally — every setting has a working loopback default;
`MARKET_DATA_SCOPE` only exists for the deployed instance, whose managed identity calls
market-data with it. `agent` needs a `DATABASE_URL` of its own and an `OPENAI_API_KEY`.
That key has no managed-identity alternative the way the database does — OpenAI is not in
Entra — so production reads the same value from Key Vault (`openai-api-key`) and
`config.py` refuses to start without it. `MARKET_MCP_URL` is the one setting whose
*absence* is a working configuration rather than a mistake: without it the agent has no
tools, which is what it was before it had any. There are three of that shape now —
`TEAMS_MCP_URL` since `add-teams-mcp`, `TRADING_MCP_URL` since
`agent-gets-the-trading-tools` — and all three are checked independently: clearing one
takes its tools away and leaves the other two exactly where they are. The third is the one
whose absence reads least like a setting: the operator asks about their positions and the
agent says it cannot see them, which sounds like the account being unreachable. An `.env`
copied before either change is the usual reason a local agent answers from memory while
market-mcp sits there idle — `dev.sh`/`dev.ps1` say so at startup rather than leave it to
be discovered.

`teams` needs the same three — `DATABASE_URL`, `OPENAI_API_KEY`, `MODELS` — and none of
them are agent's: a **separate** OpenAI key (`teams-openai-api-key` in Key Vault, so the
experiments' cost has its own line) and a catalogue of its own, with no `DEFAULT_MODEL_ID`,
because every agent in a saved team revision names its own model. `MARKET_MCP_URL` is
optional here too, with a sharper consequence than agent's: a team whose agents were
assigned tools refuses to run rather than answer without them. `TRADING_MCP_URL` is the
same setting for the write tools, checked independently — clearing it takes the order tools
away and leaves the reading ones exactly where they were.

`teams-mcp` needs no `.env` locally either, for market-mcp's reason: every setting has a
working loopback default. What it does need is something no setting can supply — the
operator's own token, arriving per call from `agent` in `X-Operator-Authorization`. Without
it every tool refuses by design: a team created on a module's own identity would belong to
that module and be invisible to the person who asked for it.

`trading-mcp` is the exception to market-mcp's "no `.env` needed locally": it has one
required setting, `CAPITAL_GATEWAY_API_KEY`, and it must be the gateway's own
`GATEWAY_API_KEY` — the gateway checks that header on every caller, loopback included, so
there is no local mode where it can be left out. Together with the demo check it makes at
start-up, that is why this module exits rather than degrades when something is wrong, and
why both dev scripts compare the two files before starting anything.

**Terraform `apply` is the operator's job, never CI's.** CI plans only, deliberately —
applying would hand the CI principal Entra directory write access. `infra/bootstrap/` keeps
local state that *is* committed; its storage-account keys are in that file and are inert by
design (`shared_access_key_enabled = false`, verified live). Don't "fix" that by rotating.

**The agent's tools arrive at `apply`, not at deploy.** Code and infrastructure land
separately here, and this is the pairing where it shows: `agent` deployed with no
`MARKET_MCP_URL` starts, runs and answers — without tools, which is a supported state and
one its own tests walk, not a broken one. The tools appear only after the operator's
`terraform apply` sets that setting and puts the agent's managed identity into
`market-mcp`'s `allowed_applications`, and after the agent restarts. Rolling back is the
same lever: clear `MARKET_MCP_URL`, restart, and the module is what it was, with the rows
in `tool_calls` still recording what happened while it had them.

The same pairing now holds for the account: an `agent` image that can send orders sends
none until `TRADING_MCP_URL` is set *and* the agent's managed identity is in
`trading-mcp`'s own `allowed_applications`. Either one alone gives a module that asks and
is refused at the door, which is the intended half-state rather than a broken one.

## Migrations are never the operator's job

**Standing rule, for every module that owns a schema — the three that exist and every one
added later: a merge to `main` must leave production serving. No operator step between the
merge and a working application, and none after it.** A module whose deployment cannot
migrate its own database is not finished, and neither is the change that added it.

What "satisfied" means, concretely, and all three are required:

1. the deployment applies `alembic upgrade head` against that module's production database
   itself, before the new image starts serving;
2. the new tables are usable by the app's own role the moment they exist — see the grant
   trap below, which is what turns a successful migration into `permission denied`;
3. the deployment's own check fails when either of those did not happen. A check that reads
   the App Service control plane proves the site is *running the right image*, not that the
   process inside came up — `deploy-agent.yml` says so in its own comment.

The rule is written from a failure, not from taste. Production `agent` sat dark on
16 August 2026 with its database at `0005` and its image shipping `0009`, because nothing
migrated it: not the container, not `deploy-agent.yml`, and the workflow's control-plane
smoke check reported green over a container crash-looping on exit code 3.

**How it is satisfied today** (`openspec/changes/archive/…-modules-migrate-their-own-database`):
each module migrates in its own `lifespan`, through `migrate.py`, before it serves anything —
and, in `market-data`, before it writes a single candle. Two properties carry it:

- **A Postgres advisory lock** (`db.py`, `MIGRATION_LOCK_KEY`) rather than a rule against
  migrating at startup. Two instances starting together give one migration and one waiter.
  The wait is bounded and deliberately uneven: five minutes for `agent`, thirty for
  `market-data`, whose candle table is the largest thing here. A lock held by a process that
  died needs no timeout — it is session scoped and dies with the connection.
- **The module's own identity**, not the server administrator's. A table created by the app
  role belongs to it, so nothing has to be granted afterwards. This is what closed the
  `ALTER DEFAULT PRIVILEGES` trap — that grant is scoped to the role creating the object, so
  it only ever worked while one identity did all the creating (`prompt_revisions`, 15 August,
  read as `permission denied` rather than as a missing table).

`schema_version.py` still runs immediately after, and now means something narrower: an
upgrade that reported success without arriving, or an image older than the schema it found.
The second gets *more* likely under this arrangement, not less — the schema moves forward at
every deploy while a rollback moves only the code back.

What a new module with a database has to do: migrate in its own lifespan under its own lock
key, with its own identity, and have a deploy check that reaches the process rather than the
control plane. `deploy-agent.yml` reads `/health`, excluded from Easy Auth the way
`market-data`'s `/ping` is — and because the lifespan blocks until the migration finishes, a
process that answers is itself the proof that the schema is at head.

One thing stays the operator's, exactly once per database: the app role must own what it is
about to alter. `scripts/grant-schema-ownership.sql` transfers ownership of everything in
`public` and grants `CREATE` on the schema. A database that has not had this done gives a
module that will not start.

## A new field on market-data's wire

The most expensive routine change in this repo — five stops, and every one of them is
somebody's job. Nothing here needs fixing; it needs to be read before starting rather than
rediscovered from a red CI job.

**It is an OpenSpec change.** `market_data/contract.py` is a contract between modules, so
the full path applies — propose first.

| # | Where | What |
|---|---|---|
| 1 | `market_data/models.py`, or `tracking.py` / `jobs/models.py` | the field on the domain model, and the query that fills it. If it is stored, its migration in `migrations/` comes first. |
| 2 | `market_data/contract.py` | the field on the `*Out` model. The domain model is not the wire: nothing is published until it is here. |
| 3 | `modules/terminal` → `pnpm contract:generate` | rewrites `src/data/contract.generated.ts`. Never edited by hand. |
| 4 | `src/data/archive.ts`, the `mapX` for that shape | snake_case → camelCase, plus the ISO → epoch-seconds conversion a chart indexes by. |
| 5 | `src/data/types.ts`, then the component | the terminal's own shape. Nothing outside `archive.ts` ever sees a wire field. |

What catches a missed step, and what does not:

- **Stop 3 skipped** — `pnpm contract:check`, before the terminal's tests. `checks.yml`
  runs the terminal's whole job whenever `contract.py` changes, so a Python-only diff
  cannot slip past it.
- **Stops 4 and 5 half-done** — `pnpm typecheck`, in both directions: a field in `types.ts`
  with no mapper line fails the mapper's return, a mapper line with no field in `types.ts`
  fails as an excess property, and an ISO string handed to a `number` fails on the spot.
- **Stops 1 and 2 disagreeing** — *nothing fails*. A field added to the domain model and not
  to the `*Out` is simply never published. This is the one stop to check by eye.

A field on a **WebSocket** message travels a shorter route with the same rule: the models
live in `market_data/hub.py`, and `openapi.py` hangs them into the published document by
hand, because a WebSocket has no route for FastAPI to describe. Stops 3 to 5 are unchanged.

## A new indicator

Not the change above, and the two are easy to conflate. Adding one — another moving average,
another oscillator, another zone — touches exactly one file: the group's own module under
`market_data/indicators/catalogue/` (`averages.py`, `volatility.py`, `regime.py`,
`oscillators.py`, `bands.py`, `structure.py`, `zones.py`, `profile.py`), where it is
appended to that module's tuple. Not `spec.py`, which is the entry *shape*, and not
`__init__.py`, which only orders the groups — as long as the new entry's output shape
(`lines`, `markers`, `zones`, `levels`) and render style are ones the catalogue and the
terminal already know. The catalogue is data, not a generated type per entry: `GET
/indicators` publishes a new entry the moment it lands there, and the terminal's picker
offers it with **zero terminal changes and no `pnpm contract:generate`** — that is the whole
point of `market-data-indicators` spec's "Katalog wystarcza do zbudowania wybieraka"
(`openspec/changes/add-technical-indicators/design.md`, "Katalog jako dane, nie jako typy").

The five-stop path above is for the rarer case this one is not: a genuinely **new output
shape**, or a **render style** (`Chart.tsx`'s `canDrawIndicator` and its sync effect, a new
`*Primitive.ts`) the terminal has no drawing code for yet. Only that touches
`market_data/contract.py`, and only then does the full route apply.

## Workflow

**First decide whether this is an OpenSpec change at all.** Open one when the work will
change a requirement (`openspec/specs/**`), a contract between modules
(`market_data/contract.py`, `capital_gateway/dtos.py`, the terminal's generated contract),
infrastructure (`infra/**`), or **an architectural rule this file calls load-bearing** —
today: "no module imports another module", and the three conditions under which source
may be shared at build time.
Otherwise: branch, tests, pull request — no proposal, no design, no review artifact. Bug
fixes, behaviour-preserving refactors, UI work that adds no requirement, documentation, CI
and tooling all take that path.

The test is mechanical — name the files the work will touch. None in those four categories
means there is nothing for a spec to say. One in them means the change is worth a
proposal.

The fourth category is younger than the others and was added because the first three read
as complete until a real change tested them: introducing workspace packages reverses the
shared-library rule outright and touches no file in categories 1–3. The mechanical test
would have waved through the most consequential architectural change on the roadmap, and
caught it only by accident, through a bundled deletion that happened to remove a
requirement.

When it *is* a change:

| Situation | Command |
|---|---|
| Think an idea through | `/opsx:explore` |
| Propose a change | `/opsx:propose` |
| Implement it | `/opsx:apply` |
| Fold it into the specs | `/opsx:archive` |

**Only `proposal.md` is unconditional.** `design.md` was already written only when there
was a decision with alternatives worth weighing; `tasks.md` and `review.md` joined it on
18 August 2026. Skipping one is a line in the proposal saying which and why — an artifact
absent on purpose reads differently from one missing.

`review.md` had been mandatory, enforced by a 256-line PreToolUse hook that refused any
archive without it. Both are gone, and the hook is the more interesting half: its previous
PowerShell version could not execute on this project's own macOS machine, so for a while
every archive passed unchecked while `settings.json` claimed a gate stood there — and its
own tests ran in no CI. A defence with no test of its failure mode is the thing this repo
stopped accepting when the audit's first iteration landed, and this one could not pass its
own rule. Write a review when the change was risky, when the verification is not obvious
from the tests, or when something turned up worth telling the next reader.

**An archived change keeps three artifacts, not five.** Once the directory has moved into
`openspec/changes/archive/`, run `scripts/trim-openspec-archive.sh`: it removes the delta
specs and the ticked `tasks.md`. The delta was merged into `openspec/specs/` by that same
archive, and what was done and when is git's, with the diffs attached. Whichever of
`proposal.md`, `design.md` and `review.md` the change wrote stay — those are what git
cannot hand back in readable form.
The rule rides in `openspec/config.yaml` under `operations.archive`, so `/opsx:archive` is
told it; `--check` in CI is what catches the archive where it was not.

**Language convention, and it is not the obvious one:** OpenSpec artifacts are written in
**Polish prose** with **English structure** — section headers, `### Requirement:`,
`#### Scenario:`, `**WHEN**`/`**THEN**`, and RFC 2119 keywords (`MUST`, `SHALL`, …) stay
literal English because the CLI parses them and `--strict` requires them. Polish "MUSI"
does not satisfy the validator. Everything else — code, comments, identifiers, commit
messages, module READMEs, this file — stays **English**. Recorded in `openspec/config.yaml`.

Validate with `openspec validate <change> --strict`.

**Comments carry the reason, not the narration.** A comment retelling the line beneath it
is something the next reader has to parse twice; one naming a measurement, a constraint or
an approach that was tried and failed is the only record of it. The essays had gathered in
the terminal — measured 10 August: ~7% comment lines in Python against 15% there — and one
deliberate pass has since trimmed the longest of them. From here it happens at the moment a
file is touched, not in bulk: rewriting comments wholesale is churn, and the reason a
comment exists is usually clearest to whoever is already reading the code around it.

## CI

`.github/workflows/checks.yml` runs on every PR to `main` and every push to it: one job per
module, running the same commands listed above, and **only for the modules the diff can
have broken** — a `changes` job works that out first. `live` tests stay out. If you touch
`market_data/contract.py`, `agent/contract.py` or `teams/contract.py`, expect the terminal's
job to run too; that is deliberate, since `contract:check` and the terminal's own
hand-written DTOs are the checks for exactly those pairings — `teams`' contract is generated
the way market-data's is (`pnpm contract:generate` reads two sources and writes a file per
source), while `agent`'s is not wired into the generator at all, so its half of that pairing
is the terminal's tests passing rather than a regenerated file. `market_data/contract.py` pulls in `market-mcp`'s job for the same
reason: that module keeps its own committed snapshot of the same schema
(`contract/market-data.openapi.json`), and `scripts/contract.py check` is what catches it
going stale. `trading-mcp` holds the same kind of snapshot one module further out —
`capital-gateway`'s whole OpenAPI document — so **any** change under the gateway runs that
job too; `teams-mcp` holds one of `teams`' document, watched through
`teams/teams/contract.py` alone, since that module prints its schema from those models; the document is built from its routes as well as its DTOs, and there is no
narrower filter that would still be true.

There is no branch protection on this repository — a private repo on the free plan cannot
have it — so a skipped job blocks nothing. If that changes, the filter needs stand-in jobs
or a required check will sit pending forever.

Seven `deploy-*.yml` workflows push images to GHCR and deploy on pushes to `main` touching
the matching module, each ending in a smoke check of the deployed thing — they differ in
how they can reach it: market-data has one path excluded from Easy Auth, market-mcp and
trading-mcp answer `/health` outright, and agent and teams have `/health` excluded and ask
the control plane which image is serving on top of it. trading-mcp's probe is the one that
proves the most for its length: that module refuses to open a port unless the gateway just
confirmed a demo account, so a 200 there means it reached the gateway, through its
firewall, with the shared key. capital-gateway is the one that cannot be probed at all — it
admits only market-data's and trading-mcp's addresses, so the control plane is the only
question its deploy can ask, which is the weaker one: it reported `Running` over a
crash-looping container on 16 August 2026.
`terraform.yml` plans on infra PRs; `terraform-apply.yml` is a manual `workflow_dispatch`
that applies — and refuses any plan touching `azuread_*`, because CI holds
`Application.Read.All` and not write. Entra changes are applied locally by the operator.

Parallel work: use `git worktree` rather than a second clone — but the dev database
container (one `compose.yaml` project, one volume), the Capital session and the fixed ports
are shared across worktrees, so only one agent at a
time can run the stack or touch migrations.
