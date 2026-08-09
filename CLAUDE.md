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
modules/market-data       Python · the candle archive. Owns the PostgreSQL. Depends on the gateway.
modules/terminal          React+TS · the operator's screen. Consumes both. Publishes nothing.
infra/                    Terraform · Azure. `infra/bootstrap/` is a separate root with local state.
openspec/                 specs (the truth) + change proposals
docs/                     architecture and reference
```

`terminal` is a consumer, not a peer — nothing depends on it. Call it the **terminal**,
never a "console" or "dashboard".

## Commands

Run these from the module directory. Nothing at the repo root builds or tests everything.

| Module | Commands |
|---|---|
| `capital-gateway` | `uv run uvicorn capital_gateway.app:app --reload --port 8010`<br>`uv run pytest` · `uv run ruff check .` |
| `market-data` | `uv run alembic upgrade head` then `uv run uvicorn market_data.app:app --reload --port 8020`<br>`uv run pytest` · `uv run ruff check .` |
| `terminal` | `pnpm dev` · `pnpm test` · `pnpm lint` · `pnpm typecheck` · `pnpm contract:check` |

Test flags that matter:

- `uv run pytest` alone runs unit tests; anything needing a database **skips** without Docker.
- `uv run pytest -m db` — integration tests against a throwaway PostgreSQL container
  (testcontainers, random port — safe to run in parallel). CI runs these.
- `uv run pytest -m live --run-live` — needs a real Capital demo session. **Never run in
  CI**, and see the session warning below.
- `--run-live-trading` (gateway only) **writes**: it opens, amends and closes demo positions.

The whole stack: `./scripts/dev.sh` (`--no-terminal` for back end only). It starts things
in dependency order — migrations → gateway → market-data → terminal — waiting for each to
actually answer. Ports are fixed: **8010** gateway, **8020** market-data, **5173** terminal.

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

**The terminal's contract is generated.** `src/data/contract.generated.ts` is built from the
schema `market-data` derives from its own models. After changing anything in
`market_data/contract.py`, run `pnpm contract:generate` in the terminal — CI's
`contract:check` fails on a stale file, and it runs before the terminal's tests on purpose.

**One Capital demo session exists.** capital.com invalidates the previous session on every
new login (`capital_gateway/client.py`), so two gateway processes on the same account
deauthenticate each other. Symptom: random 401s in both. Do not run two stacks at once.

**Env files are per-module and gitignored.** Copy from `.env.example`. The gateway needs
`CAPITAL_*` demo credentials plus its own `GATEWAY_API_KEY`; market-data needs the same
`GATEWAY_API_KEY`, a `DATABASE_URL` and the `AZURE_*` identity it connects to Postgres with.

**Terraform `apply` is the operator's job, never CI's.** CI plans only, deliberately —
applying would hand the CI principal Entra directory write access. `infra/bootstrap/` keeps
local state that *is* committed; its storage-account keys are in that file and are inert by
design (`shared_access_key_enabled = false`, verified live). Don't "fix" that by rotating.

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

**Language convention, and it is not the obvious one:** OpenSpec artifacts are written in
**Polish prose** with **English structure** — section headers, `### Requirement:`,
`#### Scenario:`, `**WHEN**`/`**THEN**`, and RFC 2119 keywords (`MUST`, `SHALL`, …) stay
literal English because the CLI parses them and `--strict` requires them. Polish "MUSI"
does not satisfy the validator. Everything else — code, comments, identifiers, commit
messages, module READMEs, this file — stays **English**. Recorded in `openspec/config.yaml`.

Validate with `openspec validate <change> --strict`.

## CI

`.github/workflows/checks.yml` runs on every PR to `main` and every push to it: one job per
module, running the same commands listed above, and **only for the modules the diff can
have broken** — a `changes` job works that out first. `live` tests stay out. If you touch
`market_data/contract.py`, expect the terminal's job to run too; that is deliberate, since
`contract:check` is the check for exactly that pairing.

There is no branch protection on this repository — a private repo on the free plan cannot
have it — so a skipped job blocks nothing. If that changes, the filter needs stand-in jobs
or a required check will sit pending forever.

Three `deploy-*.yml` workflows push images to GHCR and deploy on pushes to `main` touching
the matching module, each ending in a smoke check of the deployed thing.
`terraform.yml` plans on infra PRs; `terraform-apply.yml` is a manual `workflow_dispatch`
that applies — and refuses any plan touching `azuread_*`, because CI holds
`Application.Read.All` and not write. Entra changes are applied locally by the operator.

Parallel work: use `git worktree` rather than a second clone — but the dev database
container (one `compose.yaml` project, one volume), the Capital session and the fixed ports
are shared across worktrees, so only one agent at a
time can run the stack or touch migrations.
