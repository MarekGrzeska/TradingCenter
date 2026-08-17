# teams

Operator-defined teams of agents, saved to a catalogue and run by hand for experiments on
the demo account. A team's definition is data — a graph of roles and dependencies,
versioned append-only — compiled to a run rather than written as code. This phase writes
no order: a run ends in a recommendation kept in its trace, not a position.

Full shape of the module — the catalogue, a run's execution, the terminal's canvas — is
in `openspec/changes/add-teams-module/` (`proposal.md`, `design.md`, the `teams-*` and
`terminal-teams` delta specs). **This README describes what exists in the code today**:
the module starts, authenticates the same way `agent` and `market-data` do, migrates its
own database, serves the **catalogue** — teams, their append-only revisions, and retiring
one — and **runs a team**: agents work in the order their dependencies allow, their trace
is written as it happens, progress is readable while it happens, and a run stops when it
reaches the cost its definition allows it. What is not here yet is the terminal's own
canvas.

## What

- `config.py` — settings and three mode switches, each refusing a configuration that
  leaves ambiguous which of two things is really in effect: the database (identity vs.
  local password) and each of the two tool servers (identity vs. loopback), checked
  separately so an error names which one is half-configured. No `default_model_id` the
  way `agent` has one: a team's definition must name a model for every agent it holds,
  so there is no session-wide fallback to have. The `SCHEDULER_*` trio at the end of the
  class is the clock's own — see "Schedules and triggers" below.
- `db.py` — the connection, in the two shapes asyncpg and SQLAlchemy each insist on;
  duplicated from `agent/db.py`, not shared. Advisory-lock key `8050`, this module's
  own port.
- `auth.py` — reads the identity a platform authenticator puts on a request, the same
  two headers `agent` and `market-data` read.
- `contract.py` — the wire shapes, and `TeamDefinition` with them: the one model that is
  both what a revision stores in JSONB and what the wire carries. What it validates is
  everything the JSON alone answers — unique agent keys, edges naming real agents, no
  isolated agent, no dependency cycle.
- `validation.py` — the rest of "can this be run", which needs something outside the
  JSON: the configured model catalogue, and the tools the tool server announces. Checked
  when a revision is *saved*; `check_runnable` is the same check again at the moment a
  saved revision is about to run, for the model dropped from the configuration since.
- `models_catalogue.py` — the models a team's agents can be assigned, cheapest first.
  A twin of `agent`'s, minus the default: a revision names a model per agent or it is
  refused, so there is nothing to fall back to.
- `store.py` — the only door to `teams` and `team_revisions`. The owner is part of every
  statement, and there is no UPDATE against `team_revisions` in it: a save appends.
- `routers/catalogue.py` — `/teams`, its revisions, and retiring a team.
- `routers/runs.py` — starting a run, reading its trace, watching it (`/runs/{id}/events`,
  server-sent), and interrupting it.
- `routers/tools.py` — `GET /tools`, so a picker is built from what the server announces
  and never from a list kept here. An unreachable server is 503 rather than an empty list:
  "nothing is announced" and "nobody could be asked" are different facts.
- `routers/usage.py` — `GET /usage`, broken down by agent and by model. Every number is a
  sum over costs written when their calls happened; nothing is recomputed at read time.
- `provider.py` — OpenAI, streamed, and the only place langchain's message classes exist.
  A twin of `agent`'s with one shape changed: a call carries a *briefing* built from an
  agent's predecessors, not a conversation, because a team has no transcript to replay.
- `scheduler/clock.py` — the module's own clock: one task in `app.py`'s lifespan that
  wakes on `SCHEDULER_POLL_INTERVAL_SECONDS`, claims what is due, and starts it through
  `start_run_on_revision` — the same function the terminal's button calls, so a run
  nobody watched went through the same checks as one somebody did.
- `routers/schedules.py` — schedules, triggers and their fire history. Every write here
  runs `validation.check_unattended` against the revision that would be put to work
  without an operator watching.
- `runner/` — how a run happens, split by what each part may know. `graph.py` compiles the
  definition to a LangGraph — one node per agent, the operator's edges, and the narrowing
  that gives each agent only its predecessors' work. `loop.py` is one agent's own
  model↔tools exchange under a round ceiling. `engine.py` is where the database, the
  statuses, the time limit and whoever is watching meet. `cost.py` holds the two ceilings:
  the run's, checked before every model call, and the team's daily one, checked before a
  run starts — a run refused halfway is a run that already spent. `trading.py` is its
  deliberate twin for orders, with one difference that is the whole point: every limit
  there is optional and an absent one means no limit at all.
- `tools/` — the sessions with the tool servers (`client.py`, the only place `mcp` is
  imported) and who gets which tools (`assignment.py`). Two servers since phase 2, kept
  in a registry rather than one connection: `market-mcp` reads the archive, `trading-mcp`
  moves the account, and each is independently optional. Both refusals that stop a run
  before an agent is called live in `assignment.py`: a server that cannot be asked *and
  is needed*, and a tool no server announces. A team assigning no tools never touches
  either, and an unreachable server nobody has a tool from never reaches the caller.
  A session lives between calls, so a tool server that restarts leaves this module holding
  one the server has forgotten — and the first call after it is refused as an unknown
  session. `client.py` reopens and sends that one call again, **once**, and only for that
  refusal: the server answers it at the session gate, before reading which tool was asked
  for, so it proves the call was not handled. A timeout is never repeated — after one, the
  effect is unknown, and a repeated write would be a second order rather than a confirmed
  first. Written from the failure: `trading-mcp` was redeployed on 17 August 2026, and the
  first call after it was an order that never went.
- `app.py` — assembly only: the lifespan, the routers mounted on it, and the tool server
  it builds without connecting. Nothing that decides anything.
- `migrations/` — the schema, as the statements a deployment actually runs: the catalogue
  (`0001`), runs and their steps (`0002`), the usage ledger (`0003`), where the operator
  left each agent on the canvas (`0004`), schedules and triggers (`0005`), and the trade
  trace (`0006`).

## Run

```bash
cp .env.example .env   # then fill in OPENAI_API_KEY and MODELS
uv run alembic upgrade head
uv run uvicorn teams.app:app --reload --port 8050
```

Needs a database: `../../compose.yaml` at the repo root starts one on `127.0.0.1:55432`,
and `./scripts/dev.sh` / `./scripts/dev.ps1` create the `teams` role and database inside
it if either is missing. By hand, if you are not using those scripts:

```sql
CREATE ROLE teams WITH LOGIN PASSWORD 'change-me';
CREATE DATABASE teams OWNER teams;
```

Does not need either tool server to start, and the difference from `agent` is worth
knowing: `MARKET_MCP_URL` left unset means every team whose agents assign **no** tools
runs normally, while a team that does assign them is refused at the moment a run starts,
naming tool access as the reason. It is not a turn answered worse — it would be several
agents guessing independently, each guess paid for. `TRADING_MCP_URL` is the same setting
for the tools that place orders, checked independently: clearing it takes the order tools
away and leaves the reading ones exactly where they were. Pointing either URL anywhere off
loopback needs its `*_SCOPE` set too, the same way a remote database needs an identity.

`alembic upgrade head` above is the local convenience, not the mechanism: **the module
migrates its own database at startup** (`migrate.py`, called from `app.py`'s lifespan),
under a Postgres advisory lock, as the module's own identity — the same arrangement
`agent` and `market-data` both run today, so there is no `GRANT` step here either, once
the database exists.

## Schedules and triggers

A team can start itself. Two ways, both rows in this module's own database rather than
anything in Azure (design.md, "Zegar w procesie modułu, nie w Azure"):

- a **schedule** — a rhythm (`recurrence`: every N minutes, hourly, daily, on named
  weekdays, on a day of the month) or the cron expression it becomes, and either a pinned
  revision or "whatever is latest at the moment of each fire", which is an explicit choice
  and never the default. A save names its timing exactly one of those two ways; a read
  publishes both, with `recurrence` empty for an expression no rhythm describes
  (`recurrence.py`). The two rhythms that repeat within a day may name weekdays as well —
  the market is shut two days in seven — and every day named is stored as none named, so
  one trigger keeps one spelling. `daily` may not name them: `daily` on chosen days is
  `weekly`, and the second spelling is refused rather than stored;
- a **trigger** — a market condition, expressed as a call to a tool this module already
  has a session for, with a field path, a comparison and a threshold. Never a locally
  computed indicator: the condition is read with the same tools an agent would use.

Both fire through `start_run_on_revision`, the same function the terminal's Run button
calls. A run nobody watched has therefore passed the same checks as one somebody did —
the model catalogue, the announced tools, the daily cost ceiling, the daily order count.

**A fire that starts nothing still leaves a row.** A schedule due while its own previous
run is still going is skipped rather than queued, and the skip is recorded with its reason
and a count, because "it did not run" and "it ran and did nothing" are answers an operator
has to be able to tell apart. `GET /schedules/{id}/fires` is that history.

**Working unattended has its own safeguards**, and they are the reason this is not simply
a cron entry:

- a schedule or trigger over a revision that carries a tool this module cannot **confirm
  is read-only** requires an explicit acknowledgement (`unattended_ack`), refused by name
  at every write. The set is read from the servers' own `readOnlyHint` at save time and it
  is the *positive* one: a declared write (`place_order`), a tool with no annotation, and a
  tool whose server could not be asked are three reasons to be unsure and one refusal —
  which is what stops an outage at save time from quietly widening what runs unattended;
- after `SCHEDULER_FAILURE_THRESHOLD` **consecutive** failed runs it disables itself and
  records why — enough failures that one bad model response is not mistaken for a broken
  schedule, few enough that a genuinely broken one does not bill through the night;
- `GET /schedules/{id}/next-fires` answers when it fires next, and `POST
  /schedules/next-fires` answers the same for a timing nobody has saved yet. The terminal
  never computes that itself: the row's own `next_fire_at` reflects the last *claim*, not a
  forecast.

**A schedule's hours are Polish wall-clock hours.** The expression is rolled forward in
`Europe/Warsaw` (`scheduler/timing.py`) and every moment leaves this module in UTC, so
`0 9 * * *` is 09:00 in Poland in July and in January both — the UTC moment is what moves
at the clock change, not the operator's morning. Two consequences worth knowing: the daily
cost ceiling still resets at UTC midnight, so the gap between that reset and a morning fire
changes by an hour twice a year; and the two nights where a wall-clock moment does not
exist or exists twice are resolved by `croniter`, with what it actually does recorded in
`tests/test_schedule_timing.py`. The zone is a constant, not a column — one operator, one
zone (design.md of `set-a-schedule-without-cron`).

> **`SCHEDULER_ENABLED` is `false` in `infra/app-service.tf`, and that is now a decision
> rather than a blocker.** It was a blocker: the acknowledgement check used to consult a
> hand-kept `STATE_CHANGING_TOOLS = frozenset()`, so it ran, passed its tests, and caught
> nothing for the whole of phase 2 — while `trading-mcp` was already announcing
> `place_order`. The check now reads the servers' own annotations (above), so the clock can
> be turned on with one setting and an `apply`; nothing in the catalogue changes when it
> is. What has never happened is the end-to-end pass on a running stack (task 8.2), and
> that is the reason to leave it off until somebody has watched it fire.

### The lever

`SCHEDULER_ENABLED=false` stops the clock without a redeploy and without touching a single
row: every schedule and trigger stays exactly where it was, disabled ones stay disabled,
and starting a run by hand keeps working (specs/teams-schedules, "Budzenie wyłączone
ustawieniem"). Turning it back on resumes from the catalogue as it stands — a schedule that
was due while the clock was off fires once, not once per missed slot.

`SCHEDULER_POLL_INTERVAL_SECONDS` (15) is how often the clock looks for something due, and
`SCHEDULER_FAILURE_THRESHOLD` (3) is the streak above. Both have working defaults; neither
needs setting locally.

## Test

```bash
uv run pytest              # unit tests — anything needing a database skips without Docker
uv run pytest -m db        # integration, against a throwaway PostgreSQL container
uv run ruff check .
uv run pyright
```

## Deploy

The module's infrastructure is in `infra/` (`app-service.tf`, `entra.tf`, `database.tf`,
`key-vault.tf`). Applying it is the operator's job and never CI's — CI plans only, on
purpose, because applying would hand the CI principal Entra directory write access.

The order below is forced by dependencies, not by preference:

0. **Confirm the model catalogue.** `var.teams_models` (`infra/variables.tf`) names models
   this root does not create and cannot verify — they are OpenAI's, reached with a key. A
   name that account does not serve passes `apply` without a word and falls over on the
   first call of the first run. Check it against `GET https://api.openai.com/v1/models`.

1. **`terraform apply -target=azurerm_linux_web_app.teams`.** The database firewall rules
   read this app's own outbound addresses off its resource, and a resource-level `for_each`
   refuses to plan against a value that is only known after apply — the same two-phase
   start `market-data` and `agent` each needed. The Entra registration and its secret come
   along as dependencies of this target; they are not a separate `-target`.

2. **`terraform apply`,** unrestricted. This is what converges the rest: the logical
   database, the firewall rules from step 1's addresses, the Key Vault access policy, and
   this module's managed identity into market-mcp's `allowed_applications`.

3. **The secret, before the first container start.**

   ```bash
   az keyvault secret set --vault-name "$(terraform -chdir=infra output -raw key_vault_name)" \
      --name teams-openai-api-key --value "<the key>"
   ```

   A key of this module's own, not `agent`'s `openai-api-key` — the cost of these
   experiments belongs on its own line. The app reads it as a `@Microsoft.KeyVault(...)`
   reference: with no value there, the reference resolves to nothing and the module
   refuses to start (`config.py` requires it), which is the intended failure.

4. **The Postgres role, once per database.** Terraform creates the `teams` database but
   not the role inside it — the server's Entra administrator does, in a `psql` session
   against `dbname=teams`, for the managed identity `terraform -chdir=infra output -raw
   teams_managed_identity_principal_id` names. Check the exact spelling of the
   principal-creation call against what the server accepts (Azure's own
   `pgaadauth_create_principal_with_oid`) before running it; that step was never written
   down when `agent`'s role was created.

   Then, in the same session, hand the database over:

   ```bash
   psql "host=psql-tradingcenter.postgres.database.azure.com port=5432 dbname=teams \
         user=<entra-admin-upn> sslmode=require" \
        -v role=app-tradingcenter-teams -f scripts/grant-schema-ownership.sql
   ```

   Idempotent, and required *before* the first deploy: the module migrates itself as its
   own identity, and `ALTER TABLE` from a role that does not own the table is refused. A
   database that has not had this done gives a module that will not start.

5. **`deploy-teams.yml`** builds the image and deploys it. Nothing migrates the database
   from outside: the module does it in its own `lifespan`, under the advisory lock, before
   it serves anything — so the smoke check asking `/health` (excluded from Easy Auth in
   `app-service.tf`) is itself the proof that the schema is at head. A check reading the
   App Service control plane instead proves the site runs the right *image*, which reported
   green over a crash-looping container on 16 August 2026.

**The clock arrives off.** `SCHEDULER_ENABLED` is `"false"` in `infra/app-service.tf`, and
that is a decision rather than an oversight: `config.py` defaults it to `true`, so leaving
it out of the app settings would *enable* it. It stays off until the gap in the "Schedules
and triggers" section above is closed — a clock that can place orders unattended, guarded
by a check that cannot see the tools it is guarding against, is not a state to deploy into.
Flipping it is one line and an `apply`; nothing in the catalogue changes either way.

**Rollback.** Nothing depends on this module, so withdrawing it touches none of the other
four. Clearing `MARKET_MCP_URL` and restarting takes the tools away and leaves the module
what it was without them, with every run already traced still in the database. Rolling the
image back moves the code back but not the schema — the known asymmetry `schema_version.py`
exists to catch.

## Contract

Published the way `market-data`'s is: FastAPI's own OpenAPI document, generated into the
terminal's types rather than copied by hand (`design.md`, "Kontrakt generowany;
`scripts/contract.mjs` przestaje być jednoźródłowy").

```bash
uv run python -m teams.openapi          # the document, from the models — nothing running
cd ../terminal && pnpm contract:generate  # rewrites src/data/contract.teams.generated.ts
```

The document is built from the routes *and* the models, so adding a route changes it even
when `contract.py` does not — `pnpm contract:check` is what catches a stale generated file.

| | |
|---|---|
| `GET /health` | outside the identity requirement, and what the deploy's smoke check asks |
| `GET /models` | the model catalogue, cheapest first — everything a picker needs |
| `GET /teams` · `POST /teams` | the catalogue, and a new team with its first revision |
| `GET /teams/{id}` · `DELETE /teams/{id}` | one entry; the delete retires it, keeping its runs |
| `POST /teams/{id}/revisions` | appends the next revision; never touches the previous one |
| `GET /teams/{id}/revisions/latest` · `/{version}` | a definition as it was saved |
| `GET /revisions/{id}` | the same definition, by the id a run names it by |
| `GET /tools` | what the tool server announces right now; `[]` when none is configured, 503 when one is and could not be asked |

Every `/teams` route answers only to the identity that saved the team, and answers a team
owned by somebody else exactly as it answers one that does not exist. `/models` is the
same for everyone — it publishes configuration, not anybody's data.
