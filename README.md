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
| [capital-gateway](modules/capital-gateway/) | capital.com — trading, deep history, a live stream. Demo only. | HTTP + WebSocket |
| [market-data](modules/market-data/) | The candle archive — what the gateway saw and does not keep. Owns a PostgreSQL. | HTTP + WebSocket |
| [market-mcp](modules/market-mcp/) | MCP tools over market-data's archive, reduced for a model rather than proxied for a chart. Read-only — no tool writes. | MCP (stdio + streamable HTTP) |
| [agent](modules/agent/) | The operator's conversation with a model — its own database, its own OpenAI key, and read-only tools over the archive through market-mcp. | HTTP, streamed |
| [teams](modules/teams/) | Teams of agents as **data**, not code — a graph the operator composes, versioned append-only, run against both tool servers. Its own database, its own OpenAI key. | HTTP + OpenAPI |
| [trading-mcp](modules/trading-mcp/) | MCP tools over the gateway's **demo account** — positions, balance, and orders a team can actually place. Network transport only, one named caller, demo checked against the gateway rather than against a setting. | MCP (streamable HTTP) |
| [teams-mcp](modules/teams-mcp/) | MCP tools over the **teams catalogue**, so a team can be built and corrected by talking to the agent instead of by dragging boxes. One named caller, and every tool acts in the operator's own name — their token travels with the call. | MCP (streamable HTTP) |
| [terminal](modules/terminal/) | The operator's screen — charts in a grid, the archive's collection, the agent panel and the teams canvas. | consumes capital-gateway, market-data, agent and teams |

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
- **React + TypeScript** (`Vite`, `pnpm`, `Tailwind`) — the terminal.

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
migrations -> capital-gateway -> market-data -> market-mcp -> trading-mcp -> teams
             -> teams-mcp -> agent
          -> teams -> terminal
```

The order is not tidiness — every arrow in it is a real dependency. `market-data`
subscribes to the gateway as it starts, `market-mcp` reads `market-data`, `trading-mcp`
asks the gateway whether it is bound to the demo account and refuses to open a port if it
is not, `agent` and `teams` ask `market-mcp` for their tool list — `teams` asks
`trading-mcp` for a second one, and `agent` reads `teams` through `teams-mcp` for a third
— and the terminal's charts read `market-data` too.
Starting anything early fills the console with retries, or — in the agent's case —
quietly produces a turn answered without tools, which is worse because nothing reports it.
Each step waits for the one before it to actually answer. Ctrl+C stops the services.

`agent` and `teams` each need `MARKET_MCP_URL` in their own `.env` to use the tools at
all, and `teams` needs `TRADING_MCP_URL` as well for the ones that place orders; every
`.env.example` has them, and both scripts say so at startup if an older `.env` does not.
The consequence differs, which is why the messages do: an agent without a tool server
answers from the model alone, while a team whose agents were *assigned* tools refuses to
run at all rather than guess.

`trading-mcp` is the one module that needs a credential even locally: the gateway checks
its `X-Gateway-Key` on every caller, loopback included, so `CAPITAL_GATEWAY_API_KEY` there
must be the gateway's own `GATEWAY_API_KEY`. Both scripts compare the two files and refuse
before anything starts — a mismatch is not a failed tool call later, it is a module that
exits during start-up, because it asks the gateway about the account before it opens a
port.

**The database is local again.** `market-data` writes to the PostgreSQL container in
[compose.yaml](compose.yaml), which the scripts start first — so Docker is a requirement for
running the stack, not only for testing it. The archive survives Ctrl+C and
`docker compose down`; only `down -v` forgets it. (For one morning this was `market_data_dev`
on the Azure server, for production fidelity; the standing tax — latency, an IP allowlist, a
yearly secret rotation — cost more than the fidelity bought, and
`openspec/changes/local-dev-database-in-docker` reversed it. Production stays in Azure.)
The scripts refuse to start if the `.env` of `market-data`, `agent` or `teams` points
`DATABASE_URL` at any host that is not loopback, and each module refuses the same at
startup: without an identity configured it does not reach beyond the machine, so pointing a
local run at production is a named error, not a quiet write.

`agent` and `teams` write to further logical databases (`agent`, `teams`) in the same
container — one Postgres server, three schemas, mirroring how production shares one server
between them. The scripts create each role and database themselves the first time they are
missing.

Useful variants:

```bash
./scripts/dev.sh --no-terminal   # back end only — what the live tests need
```

The terminal has no offline mode: candles come from `market-data` and instruments from
`capital-gateway`. Nothing is archived until an instrument is added on the terminal's
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
[`.github/workflows/checks.yml`](.github/workflows/checks.yml): seven jobs in parallel, one
per module, running the same commands a developer runs — and only for the modules the
change can have broken. A first job works out which those are from the diff; a change under
`docs/` or `infra/` runs no module suite at all.

One exception is worth knowing: the terminal's job also runs when `market_data/contract.py`,
`agent/contract.py` or `teams/contract.py` changes, even if no terminal file did, and
market-mcp's runs on the first of those three for the same reason. `contract:check` and
`scripts/contract.py check` exist to catch exactly that pairing with
`market_data/contract.py`, and `teams/contract.py` is generated the same way;
`agent/contract.py` has no generator to fail, so the terminal's own tests against its
hand-written DTOs are what catch it instead — and none of them run at all if the job never
fires. Filtering any of them out by directory would retire the check in the one case it was
written for.

| Job | Runs |
|---|---|
| `capital-gateway` | `ruff check`, `pyright`, `pytest` |
| `market-data` | `ruff check`, `pyright`, `pytest` — **including the database tests**, since the runner has Docker and `conftest` only skips them where it is absent |
| `market-mcp` | `scripts/contract.py check`, `ruff check`, `pyright`, `pytest` |
| `trading-mcp` | the same four — its snapshot is `capital-gateway`'s document, so **any** change under that module runs this job |
| `teams-mcp` | the same four — its snapshot is `teams`' document, watched through `teams/contract.py`, which is where that document is printed from |
| `agent` | `ruff check`, `pyright`, `pytest` — same database-test behaviour as market-data's; its `live` tests need a real OpenAI key and stay behind `--run-live` |
| `teams` | `ruff check`, `pyright`, `pytest` — same again; nothing in the suite reaches OpenAI or market-mcp |
| `terminal` | `contract:check`, `lint`, `typecheck`, `test` |

`contract:check` runs before the terminal's tests on purpose, and `scripts/contract.py
check` before market-mcp's for the same reason: both compare their own copy of the wire —
generated TypeScript for the terminal, a committed OpenAPI snapshot for market-mcp —
against the schema `market-data` builds from its own models, and a stale copy makes every
conclusion either suite reaches about the wire rest on an out-of-date premise. Regenerate
with `pnpm contract:generate` (terminal) or `uv run python scripts/contract.py generate`
(market-mcp) after changing a model in `market_data/contract.py`.

The `live` tests are not run — they need a real Capital demo session, and putting provider
credentials in CI to earn a green tick is a bad trade. They stay behind `--run-live`.

### Deploys and infrastructure

Pushing to `main` deploys the module that changed. Each deploy ends by checking the thing
actually answers, not merely that Azure accepted the request: `market-data` is probed on
`/ws/candles`, the one path Easy Auth lets through to the container; `market-mcp` is probed
on `/health`, excluded from Easy Auth the same way and answering a plain 200 with no trick
needed; `trading-mcp` is probed there too, where the answer proves more than liveness —
that process refuses to listen at all unless the gateway just told it the account is a demo
one, so a 200 means it reached the gateway, through its firewall, with the shared key; `agent` and `teams` ask both questions, the control plane for which image is
serving and `/health` for whether the process behind it came up; the terminal is checked on
both `/` and a tab address, because deep links have broken here before while the root kept
working. `capital-gateway` admits only market-data's and trading-mcp's addresses, so a
runner cannot reach it at all, and the control plane is the only question its deploy can
ask.

That second question is why the other four ask it. The control plane reports the state of
the *site*: on 16 August 2026 it read `Running` for the better part of an hour over an
`agent` container exiting with code 3 on every restart, and the deploy that shipped it went
green. A module that carves a health path out of Easy Auth is answerable directly — and
because these modules migrate inside their own lifespan, a process that answers at all has a
database at the revision its image was built for.

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
