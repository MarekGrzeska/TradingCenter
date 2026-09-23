# CLAUDE.md

The map, and the traps that actually bite. Anything with another home gets a pointer here
rather than a copy — that is both why this file is short and why it stops drifting. It is a
cost paid in every session, so it has a ceiling with a test: `scripts/tests/test_guide_ceiling.py`.
Raising it is a deliberate edit of that line; history belongs in `docs/` and commit messages.

## What this is

A monorepo of **independent** modules. Every module runs standalone — its own entrypoint,
dependencies, tests and README — and modules cooperate only through a published contract
(HTTP/OpenAPI or MCP).

**One process per security boundary** — the load-bearing rule: a module is a process because it
has a rule of writing nobody else has, and at runtime it reaches another only through a published
contract, never through its package, its database or its identity. Inside a process, packages of
which none imports a neighbour, and one assembly that imports all of them — held by a test that
reads the imports. **Source may be shared at build time through `packages/`**, under three
conditions in `docs/architecture.md` ("What may be shared, and what may not"). If a change seems
to need something a package cannot give it, the change is wrong, not the rule.

| Where | What |
|---|---|
| `modules/capital-gateway` | capital.com: trading, deep history, live stream. Demo only, and the only door to the provider. |
| `modules/workbench` | one process, eight packages that never import each other: the conversation (`agent`), the teams (`teams`, `teams_tools`), three archives under `/market`, `/polymarket`, `/social`, the strategy platform under `/strategy` (decides, **never touches an account**), and the one door to Telegram under `/telegram`. Seven schemas, two OpenAI keys. What each package may write: `modules/workbench/README.md`. Every package's tools reach the conversation as functions, not over MCP. |
| `modules/trading-mcp` | MCP tools over the gateway's demo account. Network transport only, one named caller (the workbench). Demo checked against the gateway, not against a setting. |
| `modules/terminal` | React+TS · the operator's screen. Consumes the others, publishes nothing. Call it the **terminal**, never a "console" or "dashboard". |
| `modules/pocket` | React+TS · the archive on a phone, and a chat with the workbench beside it. A second consumer, sharing the terminal's generated contract and none of its code. |
| `packages/tc-runtime` | database, migrations, schema check, Easy Auth, the caller-access machinery, the OpenAPI response rule. |
| `packages/tc-mcp-kit` | caller identity both ways, the upstream-refusal helper, the tool-schema slimmer, mounting a FastMCP at `/mcp`. |
| `packages/tc-openai` | the streamed OpenAI call, with tools — taken only by the workbench. Duplication is measured by `scripts/measure-duplication.py`. |
| `infra/` | Terraform · Azure. `infra/bootstrap/` is a separate root with local state. |
| `openspec/` · `docs/` | specs (the truth) and proposals · architecture and reference, true today. `docs/archive/` is the road, not the state. A new `docs/*.html` copies `docs/style-template.html`. |

In `modules/workbench` only `workbench/` — the assembly — imports the packages, mounting each former
module whole under its prefix (`workbench/assembly.py`); `tests/test_layering.py` generates the
forbidden map from its package list, so a ninth package is one entry there. Why `market-mcp`,
`teams-mcp` and five other modules no longer exist, and why `trading-mcp` still does:
`docs/architecture.md`, "The order path".

## Skills

Procedures live in `.claude/skills/`, paid for only when used: **`db-cost-check`** before anything
touches the database on a timer or per event · **`contract-sync`** after a contract changes ·
**`deploy-watch`** after a merge · **`prod-health`** when production is silent or slow ·
**`system-review`** every few weeks. `openspec-*` for changes.

## Commands

From the module directory; nothing at the repo root builds or tests everything. Every Python
module runs `uv run pytest` · `ruff check .` · `pyright`, the terminal and `pocket` `pnpm test` ·
`lint` · `typecheck` · `contract:check`. What differs is how to start it:

| Module | |
|---|---|
| `capital-gateway` | `uv run uvicorn capital_gateway.app:app --reload --port 8010` |
| `workbench` | `uv run alembic -c alembic-<chain>.ini upgrade head` for `market`, `agent`, `teams`, `polymarket`, `social`, `strategy`, `telegram` (the process runs all seven itself), then `uv run uvicorn workbench.app:app --reload --port 8030` |
| `trading-mcp` | `uv run python -m trading_mcp` (8060) · plus `uv run python scripts/contract.py check`, its snapshot of the gateway's OpenAPI |
| `terminal` | `pnpm dev` (5173) |
| `pocket` | `pnpm dev` (5174) · `--host` is what a phone on the same Wi-Fi needs |

- `uv run pytest` alone runs unit tests; anything needing a database **skips** without Docker.
- `-m db` — integration against a throwaway PostgreSQL (testcontainers). CI runs these.
- `-m live --run-live` — needs a real Capital demo session. **Never in CI.**
- `--run-live-trading` (gateway only) **writes**: it opens, amends and closes demo positions.

The whole stack: `./scripts/dev.sh` or `./scripts/dev.ps1`, thin wrappers over `scripts/dev.py`;
`uv run python scripts/dev.py --explain` prints start order, ports and why.

**Ports are fixed: 8010 gateway, 8030 workbench (REST, and each package's REST *and* `/mcp` under
its prefix), 8060 trading-mcp, 5173 terminal, 5174 pocket. 8020, 8040, 8050, 8070, 8080, 8090 and
8100 are nobody's** — a `.env` still pointing at one is a tool server that reads as down.

## Things that will bite you

**The dev database is the `compose.yaml` container**, on `127.0.0.1:55432`, started first by the
dev scripts — Docker is required to run the stack, not only to test it. Leaving `DATABASE_USER`
unset selects this local mode and narrows every database URL to loopback: a remote host is refused
at startup, by `dev.py` and `config.py` both. Production uses an Entra identity instead. Do not
"restore" dev on the Azure server; that was reversed the day it was made. The dev scripts create
each logical database and role themselves — `docker-entrypoint-initdb.d` only fires on an empty volume.

**Contracts are committed copies** — the terminal's and the pocket's generated TypeScript, and
trading-mcp's snapshot of the gateway's OpenAPI; CI fails on a stale one. After touching a
`contract.py`, an `openapi.py` or a gateway route, run the `contract-sync` skill. Why a **new
indicator** is not a contract change: `modules/workbench/market_data/README.md`.

**Env files are per-module and gitignored**; copy from `.env.example`, which is the list. The
workbench reads one `.env` and a prefix marks what is doubled on purpose — `AGENT_`/`TEAMS_DATABASE_URL`,
`_OPENAI_API_KEY` (teams bill on their own line), `_MODELS`, and `AGENT_DEFAULT_MODEL_ID` (no teams
twin: every agent names its own model) — or what is one package's own (`MARKET_`, `POLYMARKET_`,
`SOCIAL_`, `STRATEGY_`, `TELEGRAM_`). Everything else is one setting for the process, read only by
`workbench/config.py`; the gateway quartet (`GATEWAY_BASE_URL`, `_STREAM_URL`, `_API_KEY`, `_SCOPE`)
is the process's. A `.env` from before a fold carries settings read by nothing, or unprefixed ones
that refuse to start; `dev.py` names each at startup (`RETIRED_SETTINGS`).

**`TRADING_MCP_URL` is the one tool server on a network, and its *absence* is a working
configuration**: the conversation simply has no account tools — while a team whose agents were
*assigned* those tools refuses to run rather than answer without them. That asymmetry is the trap;
the symptom is the operator asking about positions and the agent saying it cannot see them.
`ALERT_DESTINATION` has the same shape: unset, the post archive and the strategy platform collect
and decide as usual and tell nobody.

**`trading-mcp` will not start on a wish.** `CAPITAL_GATEWAY_API_KEY` must be the gateway's own
`GATEWAY_API_KEY` — checked on every caller, loopback included — and it asks the gateway whether the
account is a demo one *before* it opens a port. Both dev scripts compare the two files and refuse up
front; otherwise the symptom is the whole stack going down with "a service exited".

**The gateway's door asks for different things in different places, and in production the key
opens no HTTP route at all.** Locally the shared key is the whole credential. In production the
gateway's Easy Auth requires a validated token: the workbench and `trading-mcp` present their managed
identities' tokens (`GATEWAY_SCOPE`, `CAPITAL_GATEWAY_SCOPE`) beside the key, the terminal the
operator's; the application the token names decides (`MODULE_CALLER_APPLICATION_IDS` reach
everything, the terminal the account). Two exceptions, both deliberate: `/` is the health route, and
**`/ws/stream` is the one path whose door is the shared key alone** — an authenticator in front of a
WebSocket upgrade never completes it, which killed every candle feed for an hour, so that check
lives inside the gateway's handler.

**Easy Auth authorizes an application, not a route** — so every package keeps its own caller record
(`caller_access.py`), and the workbench's root routes keep one too (`workbench/root_access.py`). The
workbench admits the operator's `az` since the door to Telegram moved in; only `/telegram`'s bots and
destinations answer it (`TELEGRAM_REST_CALLER_APPLICATION_IDS`), every other record refuses it. Both
kinds of list hold **application** ids from the token's `azp`/`appid`, never
`X-MS-CLIENT-PRINCIPAL-ID`, which names the signed-in *person* for a delegated token — measured by
deploying the opposite and refusing every request the terminal made. A package reading another's
REST goes through `tc_runtime.caller_access.in_process`, never through the platform's door.

**Capital sessions coexist.** What constrains parallel work is the rate budget — 10 req/s counted
against the **account**, so two stacks starve each other. `modules/capital-gateway/README.md`.

**Terraform `apply` is the operator's job, never CI's** — applying would hand the CI principal
Entra directory write access. `infra/bootstrap/` keeps local state that *is* committed; its
storage-account keys are inert by design (`shared_access_key_enabled = false`). Don't "fix" that by rotating.

**Settings reach the app before the image that needs them.** A route record is empty in a fresh
deployment and a required setting missing is a refused start, so an `apply` landing after the deploy
is an outage in between. `TRADING_MCP_URL` needs both the apply **and** the workbench's identity in
trading-mcp's `allowed_applications`; neither substitutes for the other. Rolling back is the same
lever: clear the setting, restart. The workbench App Service is still `app-tradingcenter-agent` — a
name here is an identity, not a label.

## Migrations are never the operator's job

**Standing rule, for every schema this repository owns: a merge to `main` must leave production
serving.** No operator step between the merge and a working application. The deployment applies
`alembic upgrade head` against every database the module owns, itself, before the new image serves;
new tables are usable by the app's own role the moment they exist; and the deployment's check fails
when either did not happen — a check reading the App Service control plane is not enough (it reported
`Running` over a crash-looping container on 16 August 2026).

Each module does this in its own `lifespan`, under a Postgres advisory lock keyed per module (in the
workbench 8020, 8030, 8050, 8070, 8080, 8090 and 8100 — each the port that package used to have), with
its own identity. Reasoning: `openspec/changes/archive/…-modules-migrate-their-own-database`.

**One thing stays the operator's, exactly once per database:** the app role must own what it is
about to alter — `scripts/grant-schema-ownership.sql`, plus `GRANT CONNECT` when a database changes
hands. The workbench needs it in every one of its seven databases, since one App Service presents one identity.

## How much test is enough

Measured 19 August 2026: as many lines of test as of production code, ~18% with no assertion of
its own. These rules stop the fifth copy; they do not lower the bar (`docs/bilans-testow.html`).

1. **A domain rule is tested once, at the lowest layer that holds it.** Above it — HTTP, the tool
   surface, the view — one test that the state reaches the wire, not the whole matrix again.
2. **Don't test other people's libraries.** The exception is a *security* rule expressed through
   one: a credential in a URL, a missing TLS, a remote host without a user.
3. **No test of implementation.** Not `getsource`, `__mro__` or `signature`, not a private
   attribute, not a re-render count, not a regex over Tailwind classes.
4. **A CRUD view gets three tests**: happy path, one error, one refusal. Sort order is a unit test
   of the sorting function, never through the DOM; "the text appears" is not a test.
5. **A shared package is tested once, in `packages/`** — a consumer gets at most one integration
   test that the real pairing works. Twin files across the workbench's surfaces are one parameterised file.
6. **`@pytest.mark.db` only where the test reads or writes the database.** Input-validation
   permutations are unit tests.
7. **Setup belongs in a fixture, data in a builder.**
8. **No performance tests in the unit suite, and no character budget on a single description.** A
   ceiling belongs on an aggregate surface with headroom — the tool surface, this file.

None of this touches where a miss is silent corruption, a second position or a leaked secret rather
than a red CI: archive integrity, trading-mcp's write path, the demo guard and every refusal to
start, fail-closed authorization, secrets never reaching a response or a log, the Capital session's
one-login/one-retry, the workbench's layering and route-collision tests, migrations under their
lock, cost limits and the trading trace, and the contracts — trading-mcp's OpenAPI snapshot, the
terminal's wire↔domain mappers, the indicator golden file.

## Workflow

**First decide whether this is an OpenSpec change at all.** Open one when the work will change a
requirement (`openspec/specs/**`), a contract between modules (`market_data/contract.py`,
`capital_gateway/dtos.py`, the terminal's generated contract), infrastructure (`infra/**`), or
**an architectural rule this file calls load-bearing** — today: "one process per security
boundary", and the three conditions under which source may be shared at build time. Otherwise:
branch, tests, pull request. Bug fixes, behaviour-preserving refactors, UI adding no requirement,
documentation, CI and tooling all take that path. The test is mechanical — name the files the work will touch.

`/opsx:explore` · `/opsx:propose` · `/opsx:apply` · `/opsx:archive`, and
`openspec validate <change> --strict`.

**Only `proposal.md` is unconditional.** The others are written when there is something for them to
hold, and skipping one is a line in the proposal saying which and why. An archived change keeps three
artifacts: `scripts/trim-openspec-archive.sh` drops the delta specs and the ticked `tasks.md`, and
`--check` in CI catches the archive where it was not run.

**Language convention, and it is not the obvious one:** OpenSpec artifacts are **Polish prose**
with **English structure** — headers, `### Requirement:`, `#### Scenario:`, `**WHEN**`/`**THEN**`
and RFC 2119 keywords stay literal English because the CLI parses them; Polish "MUSI" does not
satisfy the validator. Everything else — code, comments, identifiers, commit messages, READMEs,
this file — stays **English**.

**Comments carry the reason, not the narration.** One saying what the name and the body already
say is deleted; an unreadable fragment is fixed with a name, a split or a simpler construction,
never with a paragraph beside it. A comment stays only for **why this and not the obvious
alternative**, a **library or platform trap**, or a **design decision** in one sentence. Two lines
is the ceiling; more is a document that landed in the wrong file.

## CI

`checks.yml` runs one job per module on every PR and push to `main`, **only for the modules the diff
can have broken** — a `changes` job works that out first; `live` tests stay out. Three jobs are not a
module: `scripts`, `infra` and `openspec`. Two pairings pull in a job you would not expect: anything
under `modules/workbench/` runs the terminal's job (`contract:check` over the generated contracts is
the check for those seams), and anything under `capital-gateway` runs trading-mcp's, which holds a
committed snapshot of the gateway's whole OpenAPI document.

**There is no branch protection on this repository** — a skipped job blocks nothing.

The `deploy-*.yml` workflows deploy **after a green `checks` run of the same commit**
(`workflow_run`), gated by `scripts/deploy_gate.py` and ending in `scripts/deploy_probe.py`; after a
merge, the `deploy-watch` skill follows it and rolls a failed start back before anything else.
`workflow_dispatch` is the door around the gate. **No App Service carries an address restriction** — each door is its own authentication.
`terraform.yml` plans on infra PRs; `terraform-apply.yml` is a manual dispatch that refuses any plan
touching `azuread_*`, since CI holds `Application.Read.All` and not write.

Parallel work: use `git worktree` rather than a second clone — but the dev database container, the
Capital session and the fixed ports are shared across worktrees, so only one agent at a time can run
the stack or touch migrations.
