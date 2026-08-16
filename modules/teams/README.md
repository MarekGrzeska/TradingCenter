# teams

Operator-defined teams of agents, saved to a catalogue and run by hand for experiments on
the demo account. A team's definition is data — a graph of roles and dependencies,
versioned append-only — compiled to a run rather than written as code. This phase writes
no order: a run ends in a recommendation kept in its trace, not a position.

Full shape of the module — the catalogue, a run's execution, the terminal's canvas — is
in `openspec/changes/add-teams-module/` (`proposal.md`, `design.md`, the `teams-*` and
`terminal-teams` delta specs). **This README describes what exists in the code today**,
which is the module's skeleton: it starts, authenticates the same way `agent` and
`market-data` do, migrates its own (currently empty) database, and answers `/health`.
Nothing here serves a team yet — that lands in the changes building on top of this one.

## What

- `config.py` — settings and two mode switches, each refusing a configuration that
  leaves ambiguous which of two things is really in effect: the database (identity vs.
  local password) and the tool server (identity vs. loopback). No `default_model_id`
  the way `agent` has one: a team's definition must name a model for every agent it
  holds, so there is no session-wide fallback to have.
- `db.py` — the connection, in the two shapes asyncpg and SQLAlchemy each insist on;
  duplicated from `agent/db.py`, not shared. Advisory-lock key `8050`, this module's
  own port.
- `auth.py` — reads the identity a platform authenticator puts on a request, the same
  two headers `agent` and `market-data` read.
- `app.py` — assembly only: lifespan and (for now) a single `/health` route. Nothing
  that decides anything.
- `migrations/` — the schema, as the statements a deployment actually runs. Empty of
  actual migrations for now; the machinery (`migrate.py`, `schema_version.py`,
  `migrations/env.py`) is real and already running against zero revisions, which is a
  valid "at head" state.

## Run

```bash
cp .env.example .env   # then fill in OPENAI_API_KEY and MODELS
uv run alembic upgrade head   # no-op today — there are no revisions yet
uv run uvicorn teams.app:app --reload --port 8050
```

Needs a database: `../../compose.yaml` at the repo root starts one on
`127.0.0.1:55432`. Until the dev scripts are taught about this module (a later change
in this series), create the role and database by hand the way `agent`'s once needed:

```sql
CREATE ROLE teams WITH LOGIN PASSWORD 'change-me';
CREATE DATABASE teams OWNER teams;
```

`alembic upgrade head` above is the local convenience, not the mechanism: **the module
migrates its own database at startup** (`migrate.py`, called from `app.py`'s lifespan),
under a Postgres advisory lock, as the module's own identity — the same arrangement
`agent` and `market-data` both run today, so there is no `GRANT` step here either, once
the database exists.

## Test

```bash
uv run pytest              # unit tests — anything needing a database skips without Docker
uv run pytest -m db        # integration, against a throwaway PostgreSQL container
uv run ruff check .
uv run pyright
```

## Contract

Not yet published — this phase has no routes beyond `/health`. The catalogue and run
routers, when they arrive, publish their contract the way `market-data` does: FastAPI's
own OpenAPI document, generated into the terminal's types rather than copied by hand
(`design.md`, "Kontrakt generowany; `scripts/contract.mjs` przestaje być
jednoźródłowy").
