# agent

The operator's conversation with a model. Persists what `AgentChat.tsx` used to fake:
sessions and their transcripts, in this module's own database, with every model call
priced at the moment it happens rather than recomputed later against whatever the
cennik says today.

**Tools, all of them reads.** The model can ask `market-mcp` for candles, coverage,
indicators and levels mid-answer and carry on with what comes back — at most eight calls
per turn, a number in the code rather than a setting. Nothing here reaches
`capital-gateway`, and nothing writes anywhere: `market-mcp` publishes no tool that
changes state, and this module adds none of its own. With `MARKET_MCP_URL` unset, or the
server down, the agent answers from the model alone and says so.

## What

- `config.py` — settings and two mode switches, each refusing a configuration that
  leaves ambiguous which of two things is really in effect: the database (identity vs.
  local password) and the tool server (identity vs. loopback). The model provider has
  no such switch — OpenAI is not in Entra, so a key is the only shape there is. Also the
  model catalogue's shape (`ModelCatalogueEntry`) and its own validation — a model
  without a rate fails to parse, so it can never be started with, let alone billed as
  free.
- `db.py` — the connection, in the two shapes asyncpg and SQLAlchemy each insist on;
  same split as `market-data/db.py`, duplicated rather than shared.
- `models.py` — sessions, messages, usage rows.
- `models_catalogue.py` — the queryable catalogue built from `Settings.models`.
- `prompt.py` — the one system prompt this module runs, versioned.
- `graph.py` — the LangGraph conversation graph: a model node, a tool node, and the
  conditional edge between them. Also where the three failures a turn can hit are kept
  apart — the tool refusing, the tool server being unreachable, and the provider
  breaking are three different answers.
- `provider.py` — the OpenAI client, chosen model by catalogue entry.
- `tools/` — the session with `market-mcp` and the shapes a turn sees. The only place
  the `mcp` package is imported, the way `provider.py` is the only place langchain's
  message classes are. No committed list of tools and nothing to regenerate: MCP
  describes itself, so the contract arrives in the session that uses it.
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

Does not need `market-mcp`: `MARKET_MCP_URL` left unset means no tools, and a server
configured but not answering means the same thing for that turn. Pointing the URL
anywhere off loopback needs `MARKET_MCP_SCOPE` set too — the module refuses to start
otherwise, the same way it refuses a remote database with no identity.

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
