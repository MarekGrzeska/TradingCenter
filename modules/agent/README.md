# agent

The operator's conversation with a model. Persists what `AgentChat.tsx` used to fake:
sessions and their transcripts, in this module's own database, with every model call
priced at the moment it happens rather than recomputed later against whatever the
cennik says today.

**No tools.** The graph has one node — the model call — and nothing that reaches
`market-data` or `capital-gateway`. That is deliberate and stays deliberate until a
later change says otherwise (`openspec/changes/add-agent-chat/design.md`, Non-Goals).

## What

- `config.py` — settings and two mode switches, each refusing a configuration that
  leaves ambiguous which of two things is really in effect: the database (identity vs.
  local password) and the model provider (managed identity vs. a local key). Also the
  model catalogue's shape (`ModelCatalogueEntry`) and its own validation — a model
  without a rate fails to parse, so it can never be started with, let alone billed as
  free.
- `db.py` — the connection, in the two shapes asyncpg and SQLAlchemy each insist on;
  same split as `market-data/db.py`, duplicated rather than shared.
- `models.py` — sessions, messages, usage rows.
- `models_catalogue.py` — the queryable catalogue built from `Settings.models`.
- `prompt.py` — the one system prompt this module runs, versioned.
- `graph.py` — the LangGraph conversation graph.
- `provider.py` — the OpenAI client, chosen model by catalogue entry.
- `routers/` — the HTTP surface, split by area.
- `app.py` — assembly only: lifespan and routers. Nothing that decides anything.
- `migrations/` — the schema, as the statements a deployment actually runs.

## Run

```bash
cp .env.example .env   # then fill in OPENAI_API_KEY and MODELS
uv run alembic upgrade head
uv run uvicorn agent.app:app --reload --port 8030
```

Needs a database: `../../compose.yaml` at the repo root starts one on
`127.0.0.1:55432` (`./scripts/dev.sh` / `./scripts/dev.ps1` create the `agent` database
inside it if it does not exist yet).

## Test

```bash
uv run pytest              # unit tests — anything needing a database skips without Docker
uv run pytest -m db        # integration, against a throwaway PostgreSQL container
uv run ruff check .
uv run pyright
```

## Contract

FastAPI serves its own OpenAPI at `/openapi.json`; the terminal's DTOs
(`modules/terminal/src/agent/agentApi.ts`) are written by hand against it rather than
generated — this module's contract is not wired into `pnpm contract:generate`, which is
market-data's alone (design.md, "Kontrakt terminala pisany ręcznie, bez generatora").
