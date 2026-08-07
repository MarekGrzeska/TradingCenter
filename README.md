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
| [terminal](modules/terminal/) | The operator's screen — charts in a grid, fed by the gateway or by a mock. | consumes the gateway |

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

Every module starts on its own with its own documented command. `scripts/dev.ps1` is a
convenience wrapper; neither module depends on it.

```powershell
./scripts/dev.ps1                # terminal only, on its offline mock source
./scripts/dev.ps1 -WithGateway   # plus capital-gateway, for live demo data
```

The terminal defaults to a mock data source, so the plain form needs no credentials and no
network. `-WithGateway` additionally starts the gateway, waits for it to answer, and prints
both addresses; either form stops everything it started on Ctrl+C.

## Workflow

| Situation | Command |
|---|---|
| Think an idea through | `/opsx:explore` |
| Propose a change | `/opsx:propose` |
| Implement it | `/opsx:apply` |
| Fold it into the specs | `/opsx:archive` |

OpenSpec artifacts are written in **Polish**, with English structure and RFC 2119 keywords
— the CLI parses the structure, and `--strict` requires a literal `SHALL` or `MUST`. The
convention is recorded in [openspec/config.yaml](openspec/config.yaml). Code, comments,
commits and module READMEs stay English.
