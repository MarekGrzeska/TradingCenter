# agent

The operator's conversation with a model. Persists what `AgentChat.tsx` used to fake:
sessions and their transcripts, in this module's own database, with every model call
priced at the moment it happens rather than recomputed later against whatever the
cennik says today.

**Three tool servers, and one of them writes.** The model can ask `market-mcp` for
candles, coverage, indicators and levels mid-answer, build and run teams through
`teams-mcp`, and read *and move* the demo account through `trading-mcp` — positions,
balance and working orders on the reading side, orders sent, closed, amended and
cancelled on the other. At most eight calls per turn, a number in the code rather than a
setting. Each server is configured and fails on its own: one being absent or unreachable
costs the model that server's tools and nothing else, and with all three unset the agent
answers from the model alone and says so.

`trading-mcp`'s four writing tools are the reason two things here look different from the
rest of the module. Their trace is written **before** the call is sent and settled after
it, so a turn that dies mid-order still leaves the row — with the outcome recorded as
`unknown`, which is neither a failure nor an absence (`specs/agent-trading`). And nothing
in this module caps an order's size or counts orders: the account is a demo one, enforced
by `trading-mcp` against the gateway before it opens a port, and that is the guard rather
than a number nobody can raise.

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

## Packages it takes

`tc-runtime` (database, migrations, schema check, Easy Auth principal, `GET /models`) and
`tc-openai` (the streamed call). Both are **build-time** path dependencies compiled into
this module's image — no module imports another module.

## Run

```bash
cp .env.example .env   # then fill in OPENAI_API_KEY and MODELS
uv run alembic upgrade head
uv run uvicorn agent.app:app --reload --port 8030
```

Needs a database: `../../compose.yaml` at the repo root starts one on
`127.0.0.1:55432` (`./scripts/dev.sh` / `./scripts/dev.ps1` create the `agent` database
inside it if it does not exist yet).

`alembic upgrade head` above is the local convenience, not the mechanism: **the module
migrates its own database at startup** (`migrate.py`, called from `app.py`'s lifespan),
so running it by hand only saves the first start a few seconds. Production has no step of
its own at all — a merge to `main` leaves it serving.

Two things hold that up. Migrations run under a Postgres advisory lock (`db.py`), so two
instances starting together produce one migration and one waiter rather than a race. And
they run as the module's **own** identity, not the server administrator's, which means
every table they create belongs to the role that will read it — the reason there is no
`GRANT` step here any more. That was the other half of the old arrangement and the half
with no check on it: `prompt_revisions` was invisible to the app on 15 August, reading as
`permission denied` rather than as a missing table.

`schema_version.py` still runs, immediately after. It now catches the narrower pair the
migration cannot fix: an upgrade that reported success without arriving, and an image
older than the schema it found — the second being a rollback that moved the code back and
left the database where it was.

Needs none of the three tool servers: `MARKET_MCP_URL`, `TEAMS_MCP_URL` and
`TRADING_MCP_URL` left unset each mean no tools from that one, and a server configured but
not answering means the same thing for that turn. Pointing any of the three off loopback
needs its own `*_SCOPE` set too — the module refuses to start otherwise, the same way it
refuses a remote database with no identity, and the message names which server it is
about.

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
