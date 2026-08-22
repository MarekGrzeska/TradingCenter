# workbench

The operator's conversation with a model, and the teams of agents they compose — **one
process over two schemas**.

They were two modules until 20 August 2026, and what separated them turned out to be mostly
the separation itself: twin tool clients, twin registries, twin providers, twin catalogues,
twelve settings that existed twice, and a whole third module — `teams-mcp` — whose only
reason to exist was that the conversation built teams at a neighbour's address. What is here
is the same behaviour with one process, one image and one App Service under it
(`openspec/changes/agent-and-teams-one-workbench`).

## The four packages, and the rule between them

| Package | What |
|---|---|
| `agent/` | the conversation: sessions, transcripts, streamed turns, the chart and drawing tools it owns, and every model call priced at the moment it happens |
| `teams/` | teams as **data** — a graph the operator composes, versioned append-only, its runs, their cost, and the clock that fires a schedule |
| `teams_tools/` | the MCP tools that build and run a team by talking, reaching the teams routes in this same process |
| `workbench/` | the assembly: one settings read, one FastAPI, one lifespan |

**`agent/` and `teams/` import neither each other nor `teams_tools/`; `teams_tools/` imports
neither of them; `workbench/` may import all three and is the only place that may.** That is
the second form of "no module imports another module", and it is a test rather than an
understanding — `tests/test_layering.py` reads the imports and refuses. The first convenient
dependency gets written in a hurry, and a rule with no failing case is a preference.

## Two of everything that stayed two

- **Two databases**, `agent` and `teams`, migrated in the one lifespan under separate
  advisory-lock keys. Merging the data is a separate decision nobody has taken.
- **Two OpenAI keys**, so the cost of the team experiments shows up on its own line. That
  was always about the invoice and never about the process boundary.
- **Two model catalogues**, `AGENT_MODELS` and `TEAMS_MODELS`. Only the conversation has a
  default: every agent in a saved team revision names its own model.

Everything else is one setting for the whole process — `workbench/config.py` is the only
code that reads the environment, and both surfaces' own `Settings` are built from it by
argument, with every validator they had.

## Three tool servers on a network, and two sources that are not

The model can ask **market-data** for candles, coverage, indicators and levels mid-answer,
read *and move* the demo account through **trading-mcp** — positions, balance and working
orders on the reading side, orders sent, closed, amended and cancelled on the other — and
ask **polymarket-data** what a prediction market prices an event at, of its archive or of
the provider live. At most eight calls per turn, a number in the code rather than a setting.
Each server is configured and fails on its own: one being absent or unreachable costs the
model that server's tools and nothing else.

The third pair, `POLYMARKET_MCP_URL` / `POLYMARKET_MCP_SCOPE`, is shaped exactly like the two
before it and read once for both surfaces. Three of that server's nine tools write, which is
the one place it differs from market-data's read-only surface — and what they write is a
watch list, not an account. Nothing this system does on Polymarket touches money.

The **team tools** are the fourth source and they are not on a network at all. They keep every
name, description, ceiling and refusal they had as a module; what went is the transport.
They still reach the teams routes through their own contract — `httpx.ASGITransport` on this
application — rather than calling `teams/store/`, because the owner filter, the revision
validation, the daily cost limit and the tool-catalogue check live in those routers, and a
tool reaching past them would be the access policy written a second time.

What travels with a tool call is the **operator's principal**, taken off the chat request
being served. Not their bearer token: a token needs an authenticator to mean anything, and
there is none between the conversation and the routes any more. The identity has already
been through one.

`trading-mcp`'s four writing tools are the reason two things here look different from the
rest of the module. Their trace is written **before** the call is sent and settled after it,
so a turn that dies mid-order still leaves the row — with the outcome recorded as `unknown`,
which is neither a failure nor an absence (`specs/agent-trading`). And nothing here caps an
order's size or counts orders: the account is a demo one, enforced by `trading-mcp` against
the gateway before it opens a port, and that is the guard rather than a number nobody can
raise.

## A team's memory

A team keeps notes between runs — `team_memories`, keyed by the **team** rather than by a
revision or a run, so what one run works out the next one can read whichever revision it
runs on. Inside the revision it would mint a definition per note, and two runs of "the same"
revision would stop being comparable, which is the reason a team would want to remember
anything at all.

Two tools, `memory_read` and `memory_write`, announced by **a source that is this process
itself** — no address, no identity, no session. It is the same shape as the team tools
above, on the other surface: those join the conversation's registry, this one joins the
teams registry beside `market-mcp`, `trading-mcp` and `polymarket-mcp`. Announcing them touches no database
(the descriptors are constants), which is what lets the save-time paths build a registry out
of settings alone and still publish the names; calling them needs the pool, and by then
there is a run. Which agent may read and which may write is the mechanism that was already
there: the names a definition assigns that agent. There is no new field and no second
permission system, so no saved revision had to be rewritten.

Entries are never updated. A correction is the next note, and the only deletion is the
operator's, one entry at a time through `GET`/`DELETE /teams/{id}/memory` — no tool handed
to an agent removes anything, which is deliberate: an agent that could delete would have a
way to wipe its own mistake out of the record. Three ceilings live in the code beside
`ROUND_CEILING` rather than in settings — note length (also a CHECK in migration 0008),
notes returned per read, notes written per run — because they bound the shape in which this
module hands anything to a model, and that is not the operator's budget to move.

## Route surface

Every path is where it was, except the two that collided. `GET /models` and `GET /usage`
existed on both surfaces with different answers, so the teams ones are `/teams/models` and
`/teams/usage`, registered before `/teams/{team_id}` — a path parameter matches a segment
before FastAPI reads it as an `int`, so order decides, and `tests/test_route_collisions.py`
asserts the behaviour rather than the order.

## Packages it takes

`tc-runtime` (database, migrations, schema check, Easy Auth principal, `GET /models`),
`tc-openai` (the streamed call) and `tc-mcp-kit` (the upstream-refusal helper and the
tool-schema slimmer). All **build-time** path dependencies compiled into this module's
image — no module imports another module.

## Run

```bash
cp .env.example .env   # then fill in AGENT_OPENAI_API_KEY and TEAMS_OPENAI_API_KEY
uv run alembic -c alembic-agent.ini upgrade head
uv run alembic -c alembic-teams.ini upgrade head
uv run uvicorn workbench.app:app --reload --port 8030
```

Two ini files because one `alembic.ini` cannot name two `script_location`s. They exist for
running a chain by hand; the process builds its own configuration in memory and never reads
them.

Needs both databases: `../../compose.yaml` at the repo root starts a PostgreSQL on
`127.0.0.1:55432` (`./scripts/dev.sh` / `./scripts/dev.ps1` create `agent` and `teams`
inside it if they do not exist yet).

`alembic upgrade head` above is the local convenience, not the mechanism: **the process
migrates both of its databases at startup**, so running it by hand only saves the first
start a few seconds. Production has no step of its own at all — a merge to `main` leaves it
serving.

**The lifespan is all-or-nothing.** There is no mode where the conversation serves and the
teams catalogue reports itself unavailable: a half-state nobody exercises is worse than a
failure that shows, and the deploy probe reaches the process rather than the control plane,
so a process that answers is itself the proof that both chains are at head.

Two things hold that up. Each chain runs under its own Postgres advisory lock, so two
instances starting together produce one migration and one waiter rather than a race — and a
process waiting on one database never holds up the other. And they run as the module's
**own** identity, not the server administrator's, which means every table they create
belongs to the role that will read it. That was the half with no check on it before:
`prompt_revisions` was invisible to the app on 15 August 2026, reading as `permission
denied` rather than as a missing table.

`schema_version.py` still runs, immediately after each. It now catches the narrower pair the
migration cannot fix: an upgrade that reported success without arriving, and an image older
than the schema it found — the second being a rollback that moved the code back and left the
database where it was.

Needs no network tool server: `MARKET_MCP_URL`, `TRADING_MCP_URL` and `POLYMARKET_MCP_URL`
left unset each mean no tools from that one, and a server configured but not answering means
the same thing for that turn. Pointing any of them off loopback needs its own `*_SCOPE` set too — the process
refuses to start otherwise, the same way it refuses a remote database with no identity, and
the message names which server it is about. There is no setting for the team tools and there
cannot be: a source in this process has no address to leave unset.

## Deploy

One image, one App Service — and it is still called `app-tradingcenter-agent`. A name there
is an identity rather than a label: the managed identity takes it, `DATABASE_USER` *is* that
identity, and its application id sits on three allow-lists in two other modules. Renaming
buys a hostname and costs new roles in both databases plus three edits elsewhere
(`agent-and-teams-one-workbench/design.md`, D2).

One operator step, exactly once: that role must exist and own the schema in **both**
databases (`scripts/grant-schema-ownership.sql`). One App Service presents one identity, so
the `teams` database needs the role the `agent` database already had.

## Test

```bash
uv run pytest              # unit tests — anything needing a database skips without Docker
uv run pytest -m db        # integration, against two throwaway PostgreSQL containers
uv run ruff check .
uv run pyright
```

Three suites under `tests/`, one per package that has behaviour, and one shared
`conftest.py` — the Docker probe, `--run-live` and the environment a developer's machine has
were a byte-identical copy in two of them.

## Contract

FastAPI serves its own OpenAPI at `/openapi.json`. The teams surface's document is generated
into the terminal by `pnpm contract:generate` (`python -m teams.openapi`, printing that
surface's own routers and prefixes rather than the whole process's); the conversation's DTOs
(`modules/terminal/src/agent/agentApi.ts`) are written by hand against it instead, and the
terminal's own tests are what catch a drift there.
