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
| [terminal](modules/terminal/) | The operator's screen — charts in a grid, and what the archive collects. | consumes both |

## Layout

```
modules/    one directory per module, each standalone
openspec/   specs (the truth) and change proposals
docs/       architecture and reference
```

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
database (container)  ->  migrations  ->  capital-gateway  ->  market-data  ->  terminal
```

The order is not tidiness. `market-data` subscribes to the gateway as it starts, and the
terminal's charts read `market-data`, so starting anything early only fills the console with
retries. Each step waits for the one before it to actually answer. Ctrl+C stops the services;
the database keeps running until `docker compose down`.

**Only PostgreSQL runs in a container** — see [compose.yaml](compose.yaml). The services run on
the host, where they reload on save and can be attached to; the database is the one dependency
that is a chore to install per machine and the one where everybody wanting the same version is
the point.

It listens on **55432**, not 5432. A developer machine very often already runs PostgreSQL of
its own, and Postgres.app runs one instance per installed major version on consecutive ports
from 5432 up — the machine this was written on answered on both 5432 and 5433. Colliding fails
at best; at worst it succeeds, and the archive migrates somebody else's database. The scripts
refuse to start if `modules/market-data/.env` disagrees with the port they are about to use.

Useful variants:

```bash
./scripts/dev.sh --no-terminal   # back end only — what the live tests need
./scripts/dev.sh --fresh         # drop the archive and start empty
```

The terminal has no offline mode: candles come from `market-data` and instruments from
`capital-gateway`. Nothing is archived until an instrument is added on the terminal's
`Instruments` tab, which is deliberate — collecting a pair holds a provider connection open
around the clock.

## Workflow

| Situation | Command |
|---|---|
| Think an idea through | `/opsx:explore` |
| Propose a change | `/opsx:propose` |
| Implement it | `/opsx:apply` |
| Fold it into the specs | `/opsx:archive` |

### Checks

Every pull request to `main`, and every push to it, runs
[`.github/workflows/checks.yml`](.github/workflows/checks.yml): three jobs in parallel, one
per module, running the same commands a developer runs.

| Job | Runs |
|---|---|
| `capital-gateway` | `ruff check`, `pytest` |
| `market-data` | `ruff check`, `pytest` — **including the database tests**, since the runner has Docker and `conftest` only skips them where it is absent |
| `terminal` | `contract:check`, `lint`, `typecheck`, `test` |

`contract:check` runs before the terminal's tests on purpose: it compares
`src/data/contract.generated.ts` against the schema `market-data` builds from its own models,
and a stale contract makes every conclusion the suite reaches about the wire rest on an
out-of-date premise. Regenerate with `pnpm contract:generate` after changing a model in
`market_data/contract.py`.

The `live` tests are not run — they need a real Capital demo session, and putting provider
credentials in CI to earn a green tick is a bad trade. They stay behind `--run-live`.

OpenSpec artifacts are written in **Polish**, with English structure and RFC 2119 keywords
— the CLI parses the structure, and `--strict` requires a literal `SHALL` or `MUST`. The
convention is recorded in [openspec/config.yaml](openspec/config.yaml). Code, comments,
commits and module READMEs stay English.
