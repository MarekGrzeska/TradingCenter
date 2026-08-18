# tc-runtime

Runtime plumbing shared by the modules that own a database or stand behind a front door.
A **build-time** dependency: resolved into each consumer's own lock and compiled into each
consumer's own image. Nothing is published, nothing is versioned, and no module imports
another module — see `docs/architecture.md`, "What may be shared, and what may not".

## What / run / test

No entrypoint; this is a library.

```
uv run pytest        # its own tests
uv run ruff check .
uv run pyright
```

A change here also runs the test job of every consumer (`.github/workflows/checks.yml`,
job `packages` plus the module filters). That is condition 3 of the sharing rule and the
whole price of the package existing: it converts a drift you could see in a diff into a
regression you could not, unless every consumer is exercised.

## Consumers

| Module | Takes |
|---|---|
| `agent` | `db`, `migrate`, `schema_version`, `auth`, `routers.models_router` |
| `teams` | `db`, `migrate`, `schema_version`, `auth`, `routers.models_router` |
| `market-data` | `migrate`, `schema_version` |
| `market-mcp`, `teams-mcp`, `trading-mcp` | `network_identity`, `detail` |

`market-data` takes the package **partially**, on purpose. Its `db.py` is 56.2% identical
to this one — 299 lines with a thirty-minute migration window for the largest table in the
repository — so it is a different file, not a copy that drifted, and it stays in the module.

## What is in here, and why exactly this

Condition 1 of the sharing rule is a number, so here are the numbers. Measured on
18 August 2026 by `scripts/measure-duplication.py`, before anything moved:

| File | Best pair | Identical |
|---|---|---|
| `db.py` | agent ↔ teams | 97.1% |
| `routers/models.py` | agent ↔ teams | 93.8% |
| `migrate.py` | agent ↔ teams | 91.8% |
| `auth.py` | agent ↔ teams | 86.4% |
| `network_identity.py` | teams-mcp ↔ trading-mcp | 86.2% |
| `schema_version.py` | agent ↔ teams | 83.8% |

Where two copies disagreed, the better one came here and the reason is in the file:
`schema_version.py` is teams' (it names the case where the *image* ships no revision;
agent's produced a sentence with a hole in it), carrying agent's own paragraph about the
15 August incident, which teams had dropped.

## What was refused, and why

Kept out on purpose, because condition 1 or 2 fails. This list exists so the next reader
does not repeat the measurement to reach the same answer:

| Candidate | Best pair | Why not |
|---|---|---|
| `market_data/db.py` | 56.2% vs this one | A different file. Its migration window is a property of the largest table here, not a parameter. |
| `server.py` (3× MCP) | 58.2% | Below the threshold, and the differences are what each server *is*. |
| `config.py` (7 modules) | 48.9% | Everything can be parameterised; the result would be one switch per consumer, which is condition 2 failing rather than passing. |
| `client.py` (3× MCP) | 32.1% | Three genuinely different upstreams. Only the `detail` helper inside them was a copy, and only that came here. |
| `errors.py` (3× MCP) | 25.0% | `trading-mcp` has 86 lines because it distinguishes a provider's refusal from an access failure; `market-mcp` has 13 because its refusal has one shape. |
| `telemetry.py` | 236 vs 70 lines | Two files with the same name. |

## The one thing this package cannot know

Which advisory-lock key a module's migrations take, and where its migrations live. Both
arrive as arguments, and every consumer keeps them in its own `runtime.py` with a test
asserting the key. That test is not ceremony: a key silently shared between two modules
would put their migrations behind one lock, in databases neither can see, and the symptom
is a start-up that hangs with no failing query to find it by.
