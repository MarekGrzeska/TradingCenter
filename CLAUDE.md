# CLAUDE.md

The map, and the traps that actually bite. Anything with another home gets a pointer here
rather than a copy — that is both why this file is short and why it stops drifting. It is a
cost paid in every session, so it has a ceiling with a test, the way the MCP tool surface
does: `scripts/tests/test_guide_ceiling.py`. Raising it is a deliberate edit of that line.

## What this is

A monorepo of **independent** modules. Every module runs standalone — its own entrypoint,
dependencies, tests and README — and modules cooperate only through a published contract
(HTTP/OpenAPI or MCP).

**No module imports another module.** The load-bearing rule: at runtime a module reaches
another only through a published contract, never through its package, its database or its
identity. **Source may be shared at build time through `packages/`**, under three conditions
that `docs/architecture.md` ("What may be shared, and what may not") carries with the
measurement that put them there. A package is resolved into each module's own lock and baked
into its own image; nothing is published or versioned. If a change seems to need something a
package cannot give it, the change is wrong, not the rule.

| Where | What |
|---|---|
| `modules/capital-gateway` | capital.com: trading, deep history, live stream. Demo only, and the only door to the provider. |
| `modules/market-data` | the candle archive and its own indicators. Owns the PostgreSQL. Two surfaces: the REST contract, and eleven read-only MCP tools at `/mcp` — reduced for a model, no tool writes. |
| `modules/workbench` | the operator's conversation with a model, the teams they compose, **and the prediction-market archive** — one process, three packages that never import each other (`agent`, `teams`, `polymarket_data`), three schemas, two OpenAI keys. The archive is served under `/polymarket`: its REST contract, its `/mcp` (two tools **write**, both only *add*; removing an observation is REST-only), and the only door to Polymarket. Its tools reach the conversation as functions, not over MCP. |
| `modules/trading-mcp` | MCP tools over the gateway's demo account. Network transport only, one named caller (the workbench). Demo checked against the gateway, not against a setting. |
| `modules/social-data` | the post archive: what was said, when, and what a model made of it. Owns its PostgreSQL, the door to Truth Social. Two surfaces, **nothing on either writes** — the reading is stamped with its model and overwritten, never versioned, and there is no backfill. |
| `modules/strategy` | the strategy platform. A strategy is a catalogue entry — declared facts, parameters, one pure `evaluate` — code in the image **or** an immutable revision the operator wrote. Owns its PostgreSQL, reads market-data's REST, and **never touches an account**: it decides, teams execute. |
| `modules/terminal` | React+TS · the operator's screen. Consumes the others, publishes nothing — a consumer, not a peer. Call it the **terminal**, never a "console" or "dashboard". |
| `modules/pocket` | React+TS · the archive on a phone, and a chat with the workbench beside it — mobile-first, no MCP of its own. A second consumer, sharing the terminal's generated contract and none of its code. |
| `modules/telegram-gateway` | the one door to Telegram. Any module sends a notification; it creates its own bots, and remembers nothing it sent. |
| `packages/tc-runtime` | database, migrations, schema check, Easy Auth, the caller-access machinery, the OpenAPI response rule. |
| `packages/tc-mcp-kit` | caller identity both ways, the upstream-refusal helper, the tool-schema slimmer, mounting a FastMCP at `/mcp`. |
| `packages/tc-openai` | the streamed OpenAI call, with tools — one file, taken only by the workbench, whose two surfaces were 79,4% identical here. Duplication across modules is measured by `scripts/measure-duplication.py`. |
| `infra/` | Terraform · Azure. `infra/bootstrap/` is a separate root with local state. |
| `openspec/` · `docs/` | specs (the truth) and proposals · architecture and reference, true today. `docs/archive/` is the road, not the state. A new `docs/*.html` copies `docs/style-template.html`. |

**Inside `modules/workbench` the rule has a second form**, because things that were modules
are packages of one: `agent/`, `teams/` and `polymarket_data/` never import each other,
`teams_tools/` imports none of them, and `workbench/` — the assembly — is the only place that
imports all of them, mounting a former module whole under a prefix (`workbench/assembly.py`).
`tests/test_layering.py` reads the imports and refuses; it is a test, not an understanding. This
is `one-process-per-security-boundary` in progress: the rule's first form still holds between
the remaining modules.

Why `market-mcp` and `teams-mcp` no longer exist, and why `trading-mcp` still does, is one
measured decision each — `docs/architecture.md`, "The order path".

## Commands

From the module directory; nothing at the repo root builds or tests everything. Every Python
module runs `uv run pytest` · `ruff check .` · `pyright`, the terminal and `pocket` `pnpm test` ·
`lint` · `typecheck` · `contract:check`. What differs is how to start it:

| Module | |
|---|---|
| `capital-gateway` | `uv run uvicorn capital_gateway.app:app --reload --port 8010` |
| `market-data` | `uv run alembic upgrade head`, then `uv run uvicorn market_data.app:app --reload --port 8020` |
| `workbench` | three chains — `uv run alembic -c alembic-agent.ini upgrade head`, `-c alembic-teams.ini` **and** `-c alembic-polymarket.ini` (the process runs all three itself) — then `uv run uvicorn workbench.app:app --reload --port 8030` |
| `trading-mcp` | `uv run python -m trading_mcp` (8060) · plus `uv run python scripts/contract.py check`, its snapshot of the gateway's OpenAPI |
| `social-data` | `uv run alembic upgrade head`, then `uv run uvicorn social_data.app:app --reload --port 8090` |
| `strategy` | `uv run alembic upgrade head`, then `uv run uvicorn strategy.app:app --reload --port 8080` |
| `terminal` | `pnpm dev` (5173) |
| `pocket` | `pnpm dev` (5174) · the dev scripts start it too; `--host` is what a phone on the same Wi-Fi needs |

- `uv run pytest` alone runs unit tests; anything needing a database **skips** without Docker.
- `-m db` — integration against a throwaway PostgreSQL (testcontainers, random port). CI runs these.
- `-m live --run-live` — needs a real Capital demo session. **Never in CI.**
- `--run-live-trading` (gateway only) **writes**: it opens, amends and closes demo positions.

The whole stack: `./scripts/dev.sh` or `./scripts/dev.ps1`, both thin wrappers over
`scripts/dev.py`, which is the implementation. Start order, ports and the reason each service
sits where it does are one table at the top of that file — `uv run python scripts/dev.py
--explain` prints it, so it is not repeated here.

**Ports are fixed: 8010 gateway, 8020 market-data (REST *and* `/mcp`), 8030 workbench (REST, and the
archive's REST *and* `/mcp` under `/polymarket`), 8060 trading-mcp, 8080 strategy, 8090 social-data,
8100 telegram-gateway (all three REST *and* `/mcp`), 5173 terminal, 5174 pocket. 8040, 8050 and 8070
are nobody's** — a `.env` still pointing at any of them is a tool server that reads as down. 8070 was
polymarket-data's until `one-process-per-security-boundary` folded it into the workbench.

## Things that will bite you

**The dev database is the `compose.yaml` container**, on `127.0.0.1:55432`, started first by
the dev scripts — Docker is required to run the stack, not only to test it. Leaving
`DATABASE_USER` unset is what selects this local mode, and it narrows the module to loopback: a
`DATABASE_URL` pointing at any remote host is refused at startup, by `dev.py` and `config.py`
both. Production uses an Entra identity instead. Do not "restore" the brief arrangement where
dev ran on the Azure server; it was reversed the same day it was made. The further databases
(`agent`, `teams`, `polymarket`, and the rest) live in that same container, and the dev scripts create each
role and database themselves — `docker-entrypoint-initdb.d` only fires on an empty volume.

**The terminal's contract is generated.** After changing `market_data/contract.py`, run
`pnpm contract:generate` in the terminal — CI's `contract:check` fails on a stale file. The
five-stop route a new field travels, and why a **new indicator** is not that change and touches
exactly one file, are in `modules/market-data/README.md`.

**Env files are per-module and gitignored**; copy from `.env.example`, which is the list. Two
things about them are not in any example file. First, the `workbench` reads one `.env` for two
surfaces, and a prefix marks the four things doubled on purpose — `AGENT_`/`TEAMS_DATABASE_URL`,
`_OPENAI_API_KEY` (two keys so teams experiments bill on their own line), `_MODELS`, and
`AGENT_DEFAULT_MODEL_ID`, which has no teams twin because every agent in a saved revision names
its own model. Everything else is one setting for the whole process, read only by
`workbench/config.py`. Second, three traps, the same mistake at three dates: a file copied
before `market-mcp-into-market-data` points `MARKET_MCP_URL` at 8040, where nothing listens; one
copied before `agent-and-teams-one-workbench` carries `TEAMS_MCP_URL` or `POLYMARKET_MCP_URL` (read by nothing) and
carries `DATABASE_URL`, `OPENAI_API_KEY` or `MODELS` unprefixed, which refuses to start rather
than misbehaving. `dev.py` says all of it at startup.

**The five `*_MCP_URL` settings share one shape: the *absence* of each is a working
configuration**, not a mistake. Without one, the conversation simply has no tools from that
server — while a team whose agents were *assigned* those tools refuses to run rather than answer
without them, and that asymmetry is the whole trap. Which server each names, and what its tools
may do, is the module table above; `TRADING_MCP_URL` reads least like a setting, because the
symptom of its absence is the operator asking about their positions and the agent saying it cannot
see them. `social-data` and `strategy` reach the Telegram gateway over its REST contract instead,
each with its own `TELEGRAM_GATEWAY_URL` / `_SCOPE` / `ALERT_DESTINATION` — all three or none, and
none is a module that collects or decides as usual and says nothing.

**`trading-mcp` will not start on a wish.** `CAPITAL_GATEWAY_API_KEY` must be the gateway's own
`GATEWAY_API_KEY` — the gateway checks that header on every caller, loopback included — and it
asks the gateway whether the account is a demo one *before* it opens a port. Both dev scripts
compare the two files and refuse up front, because otherwise the symptom is the whole stack
going down with "a service exited".

**The gateway's door asks for different things in different places, and in production the key
opens no HTTP route at all.** Locally the shared key is the whole credential. In production, since
`the-gateway-door-authenticates`, the gateway's Easy Auth requires a validated token: `market-data`
and `trading-mcp` present tokens of their own managed identities (`GATEWAY_SCOPE`,
`CAPITAL_GATEWAY_SCOPE`) beside the key, and the terminal presents the operator's. Since
`the-key-opens-only-the-stream` the application that token names is what decides — the two modules
reach everything (`MODULE_CALLER_APPLICATION_IDS`), the terminal the account — and a caller with
only the key is refused twice, by the platform and by the module. Two exceptions, both
deliberate: `/` is the health route, and **`/ws/stream` is the one path in this system whose door
is the shared key alone** — an authenticator in front of a WebSocket upgrade intercepts it and
never completes it, which killed every candle feed for an hour on 20 August 2026, so that check
lives inside the gateway's own handler instead.

**Capital sessions coexist**, and the warning that stood here until 10 August 2026 was never
measured and was wrong. What constrains parallel work is the rate budget — 10 req/s counted against the
**account**, so two stacks starve each other — not the session. The measurement, the API key's
own password, and what a 401 storm really was are in `modules/capital-gateway/README.md`.

**Terraform `apply` is the operator's job, never CI's** — applying would hand the CI principal
Entra directory write access. `infra/bootstrap/` keeps local state that *is* committed; its
storage-account keys are in that file and are inert by design (`shared_access_key_enabled =
false`, verified live). Don't "fix" that by rotating.

**A module's tools arrive at `apply`, not at deploy.** The `workbench` deployed with no
`MARKET_MCP_URL` starts, runs and answers — without tools, a supported state its own tests walk.
They appear only after the operator's apply sets that setting **and** puts the workbench's
managed identity into market-data's `allowed_applications` **and** its
`TOOL_CALLER_APPLICATION_IDS`, and the app restarts. Neither substitutes for the other: Easy
Auth authorizes an application, not a route (`market_data/caller_access.py`). The route record
is empty in a fresh deployment, so **the settings must reach the app before the image that
enforces them does** — an apply landing after the deploy is an outage in between. Rolling back
is the same lever: clear the URL, restart. `TRADING_MCP_URL` and trading-mcp's own
`allowed_applications` are the same pairing for the account.

Both lists hold **application** ids, read from the token's `azp`/`appid` claim and never from
`X-MS-CLIENT-PRINCIPAL-ID`, which names the signed-in *person* for a delegated token — measured
on 19 August 2026 by deploying the opposite assumption and refusing every request the terminal
made. They name **one** backend caller: the conversation and the teams runner are the same App
Service, which is why its resource is still `app-tradingcenter-agent` while the module is called
`workbench`. A name here is an identity, not a label.

## Migrations are never the operator's job

**Standing rule, for every schema this repository owns: a merge to `main` must leave production
serving.** No operator step between the merge and a working application, and none after it. A
module whose deployment cannot migrate its own databases is not finished, and neither is the
change that added it.

Three things are required, and each has a failure behind it: the deployment applies
`alembic upgrade head` against every production database that module owns, itself, before the new
image serves; the new tables are usable by the app's own role the moment they exist; and the
deployment's check fails when either did not happen. A check reading the App Service control plane
proves the site is running the right image, not that the process inside came up — the weaker
question, and it reported `Running` over a crash-looping container on 16 August 2026.

Each module satisfies this in its own `lifespan`, under a Postgres advisory lock keyed per module
(`market_data/db.py` 8020, `agent/runtime.py` 8030, `teams/runtime.py` 8050 — each the port that
module used to have) and with the module's own identity, so a table it creates belongs to it. The
reasoning, the uneven lock waits and what `schema_version.py` still means are in
`openspec/changes/archive/…-modules-migrate-their-own-database`.

**One thing stays the operator's, exactly once per database:** the app role must own what it is
about to alter — `scripts/grant-schema-ownership.sql`. A database without it gives a module that
will not start, and the workbench needs it in `teams` as well as in `agent`, since one App Service
presents one identity.

## How much test is enough

Measured 19 August 2026: ~57,300 lines of test against ~57,500 of production code, of which ~18%
carried no assertion of its own. These rules stop the fifth copy; they do not lower the bar
(`docs/bilans-testow.html`).

1. **A domain rule is tested once, at the lowest layer that holds it.** Above it — HTTP, the tool
   surface, the view — one test that the state reaches the wire, not the whole matrix again.
2. **Don't test other people's libraries.** The exception that stays is a *security* rule
   expressed through one: a credential in a URL, a missing TLS, a remote host without a user.
3. **No test of implementation.** Not `getsource`, `__mro__` or `signature`, not a private
   attribute, not a re-render count, not a regex over Tailwind classes.
4. **A CRUD view gets three tests**: happy path, one error, one refusal. Sort order is a unit test
   of the sorting function, never through the DOM; "the text appears" is not a test.
5. **A shared package is tested once, in `packages/`** — a consumer gets at most one integration
   test that the real pairing works. Twin files across the workbench's two surfaces are one
   parameterised file.
6. **`@pytest.mark.db` only where the test reads or writes the database.** Input-validation
   permutations are unit tests. This is the rule with the largest effect on the day.
7. **Setup belongs in a fixture, data in a builder** — more lines than any deletion, no assertion lost.
8. **No performance tests in the unit suite, and no character budget on a single description.** A
   ceiling belongs on an aggregate surface with headroom — the tool surface, this file — never on
   one description, where it turns every edit red.

None of this touches where a miss is silent corruption, a second position or a leaked secret
rather than a red CI: archive integrity, trading-mcp's write path, the demo guard and every
refusal to start, fail-closed authorization, secrets never reaching a response or a log, the
Capital session's one-login/one-retry, the workbench's layering and route-collision tests,
migrations under their lock, cost limits and the trading trace, and the contracts — trading-mcp's
OpenAPI snapshot, the terminal's wire↔domain mappers, the indicator golden file.

## Workflow

**First decide whether this is an OpenSpec change at all.** Open one when the work will change a
requirement (`openspec/specs/**`), a contract between modules (`market_data/contract.py`,
`capital_gateway/dtos.py`, the terminal's generated contract), infrastructure (`infra/**`), or
**an architectural rule this file calls load-bearing** — today: "no module imports another
module", and the three conditions under which source may be shared at build time. Otherwise:
branch, tests, pull request. Bug fixes, behaviour-preserving refactors, UI adding no requirement,
documentation, CI and tooling all take that path. The test is mechanical — name the files the work
will touch. The fourth category exists because introducing workspace packages reverses the
shared-library rule outright while touching no file in categories 1–3.

`/opsx:explore` · `/opsx:propose` · `/opsx:apply` · `/opsx:archive`, and
`openspec validate <change> --strict`.

**Only `proposal.md` is unconditional.** The others are written when there is something for them to
hold, and skipping one is a line in the proposal saying which and why — an artifact absent on
purpose reads differently from one missing. An archived change keeps three artifacts, not five:
`scripts/trim-openspec-archive.sh` drops the delta specs and the ticked `tasks.md`, and `--check`
in CI catches the archive where it was not run.

**Language convention, and it is not the obvious one:** OpenSpec artifacts are **Polish prose**
with **English structure** — headers, `### Requirement:`, `#### Scenario:`, `**WHEN**`/`**THEN**`
and RFC 2119 keywords stay literal English because the CLI parses them; Polish "MUSI" does not
satisfy the validator. Everything else — code, comments, identifiers, commit messages, READMEs,
this file — stays **English**.

**Comments carry the reason, not the narration.** One saying what the name and the body already
say is deleted; an unreadable fragment is fixed with a name, a split into functions or a simpler
construction, never with a paragraph beside it. A comment stays only for what the code cannot be
read for: **why this and not the obvious alternative**, a **library or platform trap**, or a
**design decision** in one sentence. Two lines is the ceiling — three paragraphs is a document
that landed in the wrong file, and belongs in `docs/` or in the commit message. Swept across the
repository on 26 August 2026, so a long comment is a regression now, not a leftover.

## CI

`checks.yml` runs one job per module on every PR and push to `main`, and **only for the modules the
diff can have broken** — a `changes` job works that out first. `live` tests stay out. Three jobs are
not a module: `scripts`, `infra` and `openspec`.

Two pairings pull in a job you would not expect, and each is a real check: `market_data/contract.py`
**or anything under `modules/workbench/`** runs the terminal's job, because `contract:check` over six
generated contracts is the check for those seams; anything under `capital-gateway` runs
trading-mcp's, which holds a committed snapshot of the gateway's whole OpenAPI document — the whole
module, because a document is built from routes as well as models.

**There is no branch protection on this repository** — a private repo on the free plan cannot have
it — so a skipped job blocks nothing.

Ten `deploy-*.yml` workflows deploy **after a green `checks` run of the same commit** (`workflow_run`,
since 2 September 2026 — before that they raced the checks and won) — eight of ~25 lines calling
`_deploy-app-service.yml`, which starts with `scripts/deploy_gate.py` (did anything the image bakes in
change since the last green checks run? not since `HEAD^`, which loses a merge whose checks were
cancelled) and ends in `scripts/deploy_probe.py`, which asks whether this commit's image is the one
App Service will serve *and* whether the process inside came up; two more deploy the front ends to
Static Web Apps. `workflow_dispatch` is the door around the gate.
**No App Service in this resource group carries an address restriction at all** — measured
20 August 2026 against the opposite premise, which is why `capital-gateway` went unprobed until
then. What held its door then was its own shared key; the Easy Auth in front of it validated nothing,
because `AllowAnonymous` passed a bearer token through untouched. Both are different today (above).
`terraform.yml` plans on
infra PRs; `terraform-apply.yml` is a manual dispatch that applies and refuses any plan touching
`azuread_*`, since CI holds `Application.Read.All` and not write.

Parallel work: use `git worktree` rather than a second clone — but the dev database container, the
Capital session and the fixed ports are shared across worktrees, so only one agent at a time can run
the stack or touch migrations.
