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
| [agent](modules/agent/) | The operator's conversation with a model — its own database, its own OpenAI key. No tools yet. | HTTP, streamed |
| [terminal](modules/terminal/) | The operator's screen — charts in a grid, the archive's collection, and the agent panel. | consumes capital-gateway, market-data and agent |

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
```

Both bring the same things up in the same order:

```
migrations  ->  capital-gateway  ->  market-data  ->  market-mcp  ->  agent  ->  terminal
```

The order is not tidiness. `market-data` subscribes to the gateway as it starts, `market-mcp`
reads `market-data`, and the terminal's charts read `market-data` too, so starting anything
early only fills the console with retries; `agent` has nothing that depends on it, so it goes
last among the back ends. Each step waits for the one before it to actually answer. Ctrl+C
stops the services.

**The database is local again.** `market-data` writes to the PostgreSQL container in
[compose.yaml](compose.yaml), which the scripts start first — so Docker is a requirement for
running the stack, not only for testing it. The archive survives Ctrl+C and
`docker compose down`; only `down -v` forgets it. (For one morning this was `market_data_dev`
on the Azure server, for production fidelity; the standing tax — latency, an IP allowlist, a
yearly secret rotation — cost more than the fidelity bought, and
`openspec/changes/local-dev-database-in-docker` reversed it. Production stays in Azure.)
The scripts refuse to start if `modules/market-data/.env` or `modules/agent/.env` points
`DATABASE_URL` at any host that is not loopback, and each module refuses the same at
startup: without an identity configured it does not reach beyond the machine, so pointing a
local run at production is a named error, not a quiet write.

`agent` writes to a second logical database (`agent`) in the same container — one Postgres
server, two schemas, mirroring how production shares one server between them. The scripts
create the role and the database themselves the first time they are missing.

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
[`.github/workflows/checks.yml`](.github/workflows/checks.yml): five jobs in parallel, one
per module, running the same commands a developer runs — and only for the modules the
change can have broken. A first job works out which those are from the diff; a change under
`docs/` or `infra/` runs no module suite at all.

One exception is worth knowing: the terminal's job also runs when `market_data/contract.py`
or `agent/contract.py` changes, even if no terminal file did, and market-mcp's runs on the
first of those two for the same reason. `contract:check` and `scripts/contract.py check`
exist to catch exactly that pairing with `market_data/contract.py`; `agent/contract.py` has
no generator to fail, so the terminal's own tests against its hand-written DTOs are what
catch it instead — and none of them run at all if the job never fires. Filtering any of
them out by directory would retire the check in the one case it was written for.

| Job | Runs |
|---|---|
| `capital-gateway` | `ruff check`, `pyright`, `pytest` |
| `market-data` | `ruff check`, `pyright`, `pytest` — **including the database tests**, since the runner has Docker and `conftest` only skips them where it is absent |
| `market-mcp` | `scripts/contract.py check`, `ruff check`, `pyright`, `pytest` |
| `agent` | `ruff check`, `pyright`, `pytest` — same database-test behaviour as market-data's; its `live` tests need a real OpenAI key and stay behind `--run-live` |
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
needed; the terminal is checked on both `/` and a tab address, because deep links have
broken here before while the root kept working. `capital-gateway` admits only
market-data's addresses, so a runner cannot reach it at all — there, and for `agent`, which
carves out no path of its own from Easy Auth, the deploy confirms through the Azure control
plane instead that the site is running the image this commit built.

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
