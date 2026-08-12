# CLAUDE.md

Orientation for an agent working in this repo. `README.md` is the fuller narrative; this
file is the map and the things that will bite you if you assume the usual defaults.

## What this is

A monorepo of **independent** modules supporting trading and research. Every module runs
standalone — its own entrypoint, dependencies, tests and README — and modules cooperate
only through a published contract (HTTP/OpenAPI or typed events).

**There are no cross-module imports and no shared library.** This is the load-bearing rule
of the architecture (`docs/architecture.md`, "Why no shared library"). If a change seems to
need one, the change is wrong, not the rule.

```
modules/capital-gateway   Python · capital.com: trading, history, live stream. Demo only.
modules/market-data       Python · the candle archive and its own indicators. Owns the PostgreSQL. Depends on the gateway.
modules/agent             Python · the operator's conversation with a model. Own database, own OpenAI key. No tools yet.
modules/terminal          React+TS · the operator's screen. Consumes all three. Publishes nothing.
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
| `agent` | `uv run alembic upgrade head` then `uv run uvicorn agent.app:app --reload --port 8030`<br>`uv run pytest` · `uv run ruff check .` · `uv run pyright` |
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
in dependency order — migrations → gateway → market-data → agent → terminal — waiting for
each to actually answer. Ports are fixed: **8010** gateway, **8020** market-data, **8030**
agent, **5173** terminal.

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

`agent` writes to a second logical database (`agent`) in the same container, on the same
port — one Postgres server, two schemas, the same shape as production's own `psql-
tradingcenter` (`infra/database.tf`). The dev scripts create the role and the database
themselves if either is missing, since `docker-entrypoint-initdb.d` only ever runs against
an empty volume and would never fire for a `tradingcenter-db-data` from before `agent`
existed.

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
`agent` needs a `DATABASE_URL` of its own and an `OPENAI_API_KEY`. That key has no
managed-identity alternative the way the database does — OpenAI is not in Entra — so
production reads the same value from Key Vault (`openai-api-key`) and `config.py`
refuses to start without it.

**Terraform `apply` is the operator's job, never CI's.** CI plans only, deliberately —
applying would hand the CI principal Entra directory write access. `infra/bootstrap/` keeps
local state that *is* committed; its storage-account keys are in that file and are inert by
design (`shared_access_key_enabled = false`, verified live). Don't "fix" that by rotating.

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
or infrastructure (`infra/**`). Otherwise: branch, tests, pull request — no proposal, no
design, no review artifact. Bug fixes, behaviour-preserving refactors, UI work that adds no
requirement, documentation, CI and tooling all take that path.

The test is mechanical — name the files the work will touch. None in those three
categories means there is nothing for a spec to say, and five artifacts describing it buy
nothing. One in them means the full path, and then the paperwork is earned. The rule and
the reasoning behind it live in `openspec/config.yaml`, which feeds them to every
generated instruction.

When it *is* a change:

| Situation | Command |
|---|---|
| Think an idea through | `/opsx:explore` |
| Propose a change | `/opsx:propose` |
| Implement it | `/opsx:apply` |
| Fold it into the specs | `/opsx:archive` |

A change is not finished without a `review.md`; archiving one without it is the mistake the
gate exists to catch. The gate is `.claude/hooks/require-review.sh`, a PreToolUse hook
watching both `openspec archive` and a manual `mv` into `openspec/changes/archive/`. It
needs `bash` — which means git-bash on Windows, where it would otherwise not run at all.
After editing it, run `.claude/hooks/require-review.test.sh`; a hook that cannot execute
allows everything and reports nothing, so it is not a thing to change untested.

**An archived change keeps three artifacts, not five.** Once the directory has moved into
`openspec/changes/archive/`, run `scripts/trim-openspec-archive.sh`: it removes the delta
specs and the ticked `tasks.md`. The delta was merged into `openspec/specs/` by that same
archive, and what was done and when is git's, with the diffs attached. `proposal.md`,
`design.md` and `review.md` stay — those are what git cannot hand back in readable form.
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
`market_data/contract.py` or `agent/contract.py`, expect the terminal's job to run too;
that is deliberate, since `contract:check` and the terminal's own hand-written DTOs are the
checks for exactly those pairings — `agent`'s contract is not wired into
`pnpm contract:generate`, so its half of that pairing is the terminal's tests passing, not
a regenerated file.

There is no branch protection on this repository — a private repo on the free plan cannot
have it — so a skipped job blocks nothing. If that changes, the filter needs stand-in jobs
or a required check will sit pending forever.

Four `deploy-*.yml` workflows push images to GHCR and deploy on pushes to `main` touching
the matching module, each ending in a smoke check of the deployed thing — market-data's and
agent's differ here: market-data has one path excluded from Easy Auth to probe directly,
agent has none, so its deploy confirms through the Azure control plane instead, the same way
capital-gateway's already did.
`terraform.yml` plans on infra PRs; `terraform-apply.yml` is a manual `workflow_dispatch`
that applies — and refuses any plan touching `azuread_*`, because CI holds
`Application.Read.All` and not write. Entra changes are applied locally by the operator.

Parallel work: use `git worktree` rather than a second clone — but the dev database
container (one `compose.yaml` project, one volume), the Capital session and the fixed ports
are shared across worktrees, so only one agent at a
time can run the stack or touch migrations.
