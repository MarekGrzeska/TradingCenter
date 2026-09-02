# TradingCenter

An ecosystem of **independent** modules — services, APIs, apps, agents — that together
support trading and research. Successor to TradingHub, which keeps running while its
modules move here one at a time.

- **Monorepo**, but every module runs **standalone**: its own entrypoint, dependencies,
  tests and README. Copy a module directory, run it, it works.
- Modules cooperate only through a **published contract** — HTTP/OpenAPI, CLI, or typed
  events. **No cross-module imports.**
- Built with [OpenSpec](https://github.com/Fission-AI/OpenSpec): specs arrive
  incrementally and are expected to change.

## Modules

| Module | What | Contract |
|---|---|---|
| [capital-gateway](modules/capital-gateway/) | capital.com — trading, deep history, a live stream. Demo only, and the only door to the provider. | HTTP + WebSocket |
| [market-data](modules/market-data/) | The candle archive — what the gateway saw and does not keep. Owns a PostgreSQL. Serves two surfaces: the REST contract, and eleven read-only MCP tools at `/mcp`, reduced for a model rather than proxied for a chart. | HTTP + OpenAPI, MCP (streamable HTTP) |
| [workbench](modules/workbench/) | The operator's conversation with a model, and the teams of agents they compose — one process over two schemas. Two databases, two OpenAI keys, two model catalogues; the tools that build and run a team are a layer inside it rather than a module beside it. | HTTP + OpenAPI, streamed |
| [trading-mcp](modules/trading-mcp/) | MCP tools over the gateway's **demo account** — positions, balance, and orders a team can actually place. Network transport only, one named caller, demo checked against the gateway rather than against a setting. | MCP (streamable HTTP) |
| [polymarket-data](modules/polymarket-data/) | The prediction-market archive and the only door to Polymarket. Owns a PostgreSQL. Two surfaces like market-data — but two of its nine tools **write**, and both only add to the list of observations; an observation is collected or removed with all its history, and removing is REST-only. | HTTP + OpenAPI, MCP (streamable HTTP) |
| [social-data](modules/social-data/) | The post archive: what was said, when, and what a model made of it. Owns a PostgreSQL, the door to Truth Social. Two surfaces, and **nothing on either writes** — the reading is stamped with its model and overwritten, never versioned, and there is no backfill. | HTTP + OpenAPI, MCP (streamable HTTP) |
| [strategy](modules/strategy/) | The strategy platform. A strategy is a catalogue entry — declared facts, parameters, one pure `evaluate` — and the entry is code in the image **or** an immutable revision the operator wrote. Owns a PostgreSQL, reads market-data's REST, and **never touches an account**: it decides, teams execute. | HTTP + OpenAPI, MCP (streamable HTTP) |
| [telegram-gateway](modules/telegram-gateway/) | The one door to Telegram. Any module sends a notification; it creates its own bots, and remembers nothing it sent. | HTTP + OpenAPI, MCP (streamable HTTP) |
| [terminal](modules/terminal/) | The operator's screen — charts in a grid, the archive's collection, the agent panel, the teams canvas, and the screens the four newer archives publish. | consumes six modules |
| [pocket](modules/pocket/) | The archive on a phone, and a chat with the workbench beside it — mobile-first, two audiences, no MCP of its own. A second consumer, sharing the terminal's generated contract and none of its code. | consumes polymarket-data, social-data and workbench |

## Layout

```
modules/       one directory per module, each standalone
openspec/      specs (the truth) and change proposals
docs/          architecture and reference
docs/archive/  the road to a decision, not the state after it
```

What sits in `docs/archive/` was true when it was written and is kept for the reasoning
rather than the conclusion — cost research and two deployment plans from before Azure was
chosen, and one list of open items that are now all closed. Nothing there describes how the
system works today; `docs/` itself is meant to open at any time and contain only that.

## Stack

- **Python 3.12** (`uv`, `ruff`, `pytest`) — services, data, agents, scripts.
- **React + TypeScript** (`Vite`, `pnpm`, `Tailwind`) — the terminal and pocket.

## Local development

Every module starts on its own with its own documented command. The scripts below are
convenience wrappers; no module depends on one.

```bash
./scripts/dev.sh              # macOS and Linux
./scripts/dev.ps1             # Windows

# Both are wrappers over one implementation. `--explain` prints the start order
# and why each service sits where it does, without starting anything.
uv run python scripts/dev.py --explain
```

Both bring the same things up in the same order:

```
migrations -> capital-gateway -> market-data -> trading-mcp -> polymarket-data
           -> social-data -> strategy -> telegram-gateway -> workbench
           -> terminal -> pocket
```

The order is not tidiness — every arrow in it is a real dependency, and `dev.py --explain`
prints the reason for each rather than repeating it here. In short: `market-data` subscribes
to the gateway as it starts; `trading-mcp` asks the gateway whether it is bound to the demo
account and refuses to open a port if it is not; the three archives after it answer to their
own upstreams and wait on nothing above them; `strategy` reads market-data's REST; the
`workbench` reads six tool lists on the first turn that wants one; the front ends read the
back ends. Starting anything early fills the console with retries, or — in the
conversation's case — quietly produces a turn answered without tools, which is worse because
nothing reports it. Each step waits for the one before it to actually answer. Ctrl+C stops
the services.

The chain used to be shorter, and both directions are real: `teams` and `teams-mcp` became
the workbench, taking three arrows out, and five modules have been added since.

The `workbench` reads six tool-server settings, and the *absence* of each is a working
configuration rather than a mistake: `MARKET_MCP_URL` for the archive's tools,
`TRADING_MCP_URL` for the ones that place orders, `POLYMARKET_MCP_URL`, `SOCIAL_MCP_URL`
and `TELEGRAM_MCP_URL` for the next three, and `STRATEGY_MCP_URL` for the one a trigger reads
to wake a team. `.env.example` has all six, and the scripts say
so at startup if an older `.env` does not — including when it still carries a setting this
merge stopped reading, such as `TEAMS_MCP_URL`. The consequence of each absence differs,
which is why the messages do: the conversation without a tool server's tools answers from the
model alone, while a team whose agents were *assigned* tools refuses to run at all rather than
guess. `social-data` and `strategy` reach the Telegram gateway over its REST contract instead,
each with its own `TELEGRAM_GATEWAY_URL` — all of that module's settings or none, and none is
a module that collects or decides as usual and says nothing.

`trading-mcp` is the one module that needs a credential even locally: the gateway checks
its `X-Gateway-Key` on every caller, loopback included, so `CAPITAL_GATEWAY_API_KEY` there
must be the gateway's own `GATEWAY_API_KEY`. Both scripts compare the two files and refuse
before anything starts — a mismatch is not a failed tool call later, it is a module that
exits during start-up, because it asks the gateway about the account before it opens a
port.

**The database is local again.** Every module that owns one writes to the PostgreSQL
container in [compose.yaml](compose.yaml), which the scripts start first — so Docker is a
requirement for running the stack, not only for testing it. The archives survive Ctrl+C and
`docker compose down`; only `down -v` forgets them. (For one morning this was `market_data_dev`
on the Azure server, for production fidelity; the standing tax — latency, an IP allowlist, a
yearly secret rotation — cost more than the fidelity bought, and
`openspec/changes/local-dev-database-in-docker` reversed it. Production stays in Azure.)
The scripts refuse to start if any module's `DATABASE_URL` — or either of the workbench's
two, `AGENT_DATABASE_URL` and `TEAMS_DATABASE_URL` — points at any host that is not
loopback, and each module refuses the same at startup: without an identity configured it
does not reach beyond the machine, so pointing a local run at production is a named error,
not a quiet write.

Seven logical databases live in that one container — `market_data`, `agent`, `teams`,
`polymarket`, `social`, `strategy`, `telegram` — mirroring how production shares one server
between them. Each module migrates its own at startup under its own advisory lock, and the
workbench migrates both of its chains before it serves anything. The scripts create each role
and database themselves the first time they are missing; `docker-entrypoint-initdb.d` only
fires on an empty volume, which is why the scripts and not the image do it.

Useful variants:

```bash
./scripts/dev.sh --no-terminal   # back ends only — what the live tests need
```

Neither front end has an offline mode: the terminal's candles come from `market-data` and
its instruments from `capital-gateway`, and pocket reads the two newest archives and the
workbench. Nothing is archived until an instrument is added on the terminal's
`Instruments` tab, which is deliberate — collecting a pair holds a provider connection open
around the clock.

## Workflow

Not every change is an OpenSpec change. One is opened when the work will change a
**requirement** (`openspec/specs/`), a **contract between modules**, or **infrastructure**
(`infra/`). Everything else — bug fixes, refactors that keep behaviour, UI work adding no
requirement, documentation, CI — is a branch, its tests and a pull request. That is not a
lesser path and it skips no review; it skips paperwork describing work no spec has an
opinion about. The rule is in [openspec/config.yaml](openspec/config.yaml), where the CLI
reads it into every set of instructions it generates.

When it is a change:

| Situation | Command |
|---|---|
| Think an idea through | `/opsx:explore` |
| Propose a change | `/opsx:propose` |
| Implement it | `/opsx:apply` |
| Fold it into the specs | `/opsx:archive` |

### Checks

Every pull request to `main`, and every push to it, runs
[`.github/workflows/checks.yml`](.github/workflows/checks.yml): a job per module in
parallel, running the same commands a developer runs — and only for the modules the
change can have broken. A first job works out which those are from the diff; a change under
`docs/` or `infra/` runs no module suite at all.

One exception is worth knowing: the terminal's job also runs when `market_data/contract.py`
changes, or anything at all under `modules/workbench/`, even if no terminal file did.
`contract:check` exists to catch exactly that pairing with `market_data/contract.py`, and
the workbench's teams surface is generated the same way; its conversation contract has no
generator to fail, so the terminal's own tests against its hand-written DTOs are what catch
it instead — and none of them run at all if the job never fires. The whole workbench rather
than either `contract.py`, because a document is built from routes as well as models, and
`weekdays-on-the-shorter-rhythms` merged green over exactly that.

| Job | Runs |
|---|---|
| `capital-gateway` | `ruff check`, `pyright`, `pytest` |
| `market-data` | `ruff check`, `pyright`, `pytest` — **including the database tests**, since the runner has Docker and `conftest` only skips them where it is absent, and including the tool surface it serves at `/mcp` |
| `trading-mcp` | the same three plus `contract.py check` — its snapshot is `capital-gateway`'s document, so **any** change under that module runs this job |
| `polymarket-data`, `social-data`, `strategy`, `telegram-gateway` | `ruff check`, `pyright`, `pytest` — same database-test behaviour as market-data's, each against its own container |
| `workbench` | `ruff check`, `pyright`, `pytest` — same database-test behaviour, against two containers, one per schema; its `live` tests need a real OpenAI key and stay behind `--run-live` |
| `packages` | the three build-time packages, tested once here rather than in each consumer |
| `terminal`, `pocket` | `contract:check`, `lint`, `typecheck`, `test` |
| `scripts`, `infra`, `openspec` | the repository's own tooling: `pytest` over `scripts/`, `terraform fmt`/`validate`, and `openspec validate --all --strict` with the archive-trim check |

`contract:check` runs before the terminal's tests on purpose: it compares the terminal's
generated TypeScript against the schema `market-data` builds from its own models, and a
stale copy makes every conclusion that suite reaches about the wire rest on an out-of-date
premise. Regenerate with `pnpm contract:generate` after changing a model in
`market_data/contract.py`. There used to be a second copy of that schema — market-mcp kept
a committed OpenAPI snapshot and a script that policed it — and the module holding it is a
route inside `market-data` now, so the tools read those models directly and there is
nothing left to go stale.

The `live` tests are not run — they need a real Capital demo session, and putting provider
credentials in CI to earn a green tick is a bad trade. They stay behind `--run-live`.

### Deploys and infrastructure

Pushing to `main` deploys the module that changed — ten `deploy-*.yml` workflows, eight of
them a few lines over [`_deploy-app-service.yml`](.github/workflows/_deploy-app-service.yml)
and two over the Static Web Apps action. Each deploy ends by checking the thing actually
answers, not merely that Azure accepted the request: `market-data` is probed on
`/ws/candles`, the one path Easy Auth lets through to the container — and still that one
rather than the tool surface it also serves, since `/mcp` answers nothing without a session
and a caller identity; `trading-mcp` is probed on `/health`, excluded from Easy Auth the
same way, where the answer proves more than liveness —
that process refuses to listen at all unless the gateway just told it the account is a demo
one, so a 200 means it reached the gateway, through its firewall, with the shared key; the
`workbench` and the four newer back ends ask both questions, the control plane for which
image is serving and their own health path for whether the process behind it came up; the
terminal and pocket are checked on both `/` and a tab address, because deep links have broken
here before while the root kept working. `capital-gateway` asked only the control plane until
20 August 2026, on a premise nobody had checked — that it admits only the service plan's own
outbound addresses. No App Service in this resource group carries an address restriction at
all, and its `/` answered a laptop on the first try; what holds its door is its own shared
key, checked inside the module. It probes `/` for its own name now, like every other module.

That second question is why the others ask it. The control plane reports the state of the
*site*: on 16 August 2026 it read `Running` for the better part of an hour over an `agent`
container exiting with code 3 on every restart, and the deploy that shipped it went green.
A module that carves a health path out of Easy Auth is answerable directly — and because
these modules migrate inside their own lifespan, a process that answers at all has its
databases at the revisions its image was built for. Both of them, in the workbench's case:
its lifespan does not finish until each chain has run under its own lock.

Infrastructure is applied by hand, from
[`terraform-apply.yml`](.github/workflows/terraform-apply.yml) — Actions → terraform-apply →
Run workflow, typing `apply` to confirm. It is not an approval button, because
required-reviewer rules need a paid plan on a private repository; the plan to read is the
one `terraform.yml` comments on the pull request. The workflow refuses any plan that would
change an Entra object, since CI may read the directory and not write to it — those stay
`terraform apply` on the operator's own machine.

OpenSpec artifacts are written in **Polish**, with English structure and RFC 2119 keywords
— the CLI parses the structure, and `--strict` requires a literal `SHALL` or `MUST`. The
convention is recorded in [openspec/config.yaml](openspec/config.yaml). Code, comments,
commits and module READMEs stay English.
