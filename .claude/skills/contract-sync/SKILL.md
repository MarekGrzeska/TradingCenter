---
name: contract-sync
description: Regenerate every committed contract snapshot in TradingCenter and check it — the terminal's six and the pocket's three generated TypeScript contracts (printed from the workbench packages' own Pydantic models), and trading-mcp's snapshot of capital-gateway's whole OpenAPI document — telling a real contract change from the Windows CRLF artefact. Use it after touching a `contract.py`, an `openapi.py`, a router's response model, `capital_gateway/dtos.py` or any capital-gateway route; when CI's `contract:check` or trading-mcp's `contract.py check` is red; or when asked ("zregeneruj kontrakt", "contract:check pada", "sync contracts", "kontrakt terminala"). Not for designing a contract change — that is an OpenSpec change first.
---

# Contract sync

Three consumers keep a committed copy of someone else's schema, so a change on one side shows up as
a diff beside the change that caused it — and CI fails when the copy is stale:

| Consumer | Copies of | Regenerate |
|---|---|---|
| `modules/terminal` | market-data, teams, agent, polymarket-data, social-data, strategy (`src/data/contract*.generated.ts`) | `pnpm contract:generate` |
| `modules/pocket` | social-data, polymarket-data, agent | `pnpm contract:generate` |
| `modules/trading-mcp` | capital-gateway's whole OpenAPI document — routes as well as DTOs | `uv run python scripts/contract.py generate` |

Each schema is printed from the module's own Python (`python -m <package>.openapi`), never from a
running server. So nothing needs to be started, but each module's virtualenv must exist (`uv sync`
once in `modules/workbench` and `modules/capital-gateway`).

## Run

```bash
bash .claude/skills/contract-sync/scripts/sync.sh           # regenerate all three, then check
bash .claude/skills/contract-sync/scripts/sync.sh --check   # check only, write nothing
```

It prints, per generated file, one of: **unchanged**, **line endings only** (the CRLF artefact —
nothing to commit), or **changed** with a diff stat. A *changed* file belongs in the same commit as
the change that caused it; then the consumer's own tests and `typecheck` say whether the screen
still compiles against it (`pnpm typecheck` in the terminal and the pocket).

## Reading the result

- **A field you did not touch changed** — something upstream moved (a shared model, a FastAPI
  default). Find it before committing; a contract is a promise to another module.
- **`contract:check` red in CI, green locally** — almost always a file regenerated but not committed.
- **`M` in `git status` with an empty `git diff`** — CRLF. `git diff --ignore-cr-at-eol` is empty
  too, and CI on Linux passes. Leave it, or `git checkout -- <file>`.
- **trading-mcp's check fails on a gateway change that added no field** — expected: the snapshot is
  of the whole document, routes included. Regenerate and commit it with the gateway change.

A new indicator in the candle archive is *not* a contract change and touches one file
(`modules/workbench/market_data/README.md` says why).
