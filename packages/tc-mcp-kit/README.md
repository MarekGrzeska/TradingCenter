# tc-mcp-kit

The caller-identity middleware and the upstream-refusal helper, shared by `market-data`,
`teams-mcp` and `trading-mcp`. A **build-time** dependency like `tc-runtime` — see
`docs/architecture.md`, "What may be shared, and what may not".

```
uv run pytest · uv run ruff check . · uv run pyright
```

## Why this is a package of its own, and not part of `tc-runtime`

It was, until 18 August 2026. `openspec/changes/packages-replace-the-hand-copies/design.md`,
D1, rejected a third package on the grounds that `network_identity.py` needs no MCP
dependency — it is raw ASGI — and `detail.py` needs only `httpx`, so a package for ~150
lines would cost more in three `pyproject.toml` files than it saved.

That reasoning was about what the *package* needs, not what its *consumers* would inherit.
`tc-runtime` also carries `alembic`, `sqlalchemy[asyncio]`, `asyncpg`, `azure-identity` and
`aiohttp` — for the modules that own a database. None of the three MCP modules does; they
took the whole tree for two imports. Measured on 18 August 2026, before the split:

| Module | Packages in `uv.lock` |
|---|---|
| `trading-mcp` | 70 (from 47 before `tc-runtime`) |
| `teams-mcp` | 70 (from 54) |
| `market-mcp` | 70 (from 61) |

Splitting out this package is D1's correction, not a reversal of the rule it was applying —
the rule (measured copy, parameterisable difference, every consumer tested) is unchanged.
What was wrong was measuring the package's own dependency list instead of the consumer's
resolved tree.

**The reason above stopped being the whole reason on 19 August 2026**, when `market-mcp`
became a route in `market-data` and that module took this package. "None of the consumers
owns a database" was true of the three MCP modules and is not true of `market-data`, which
owns the PostgreSQL. What survives is the half that was always doing the work: this package
carries what a module needs **to speak MCP**, and `tc-runtime` carries what a module needs
**to own a schema**. A consumer may want one, the other, or — as `market-data` now does —
both, and taking one has never implied taking the other.

## What is in here

- `network_identity.RequireCallerIdentity` — raw ASGI middleware, not Starlette's
  `BaseHTTPMiddleware` (which buffers a response body in some Starlette versions, breaking
  the streamable-http transport all three modules use). Refuses a request with no
  authenticated principal when the module's own setting requires one; the platform's own
  health probe is exempt by path, in every module, unconditionally.
- `detail.detail` — one upstream refusal, however FastAPI spelled it (a `detail` string or
  its own list of validation objects), flattened to one sentence a model can act on.
- `tool_schemas.slim_tool_schemas` — the published tool surface without the scaffolding
  pydantic emits: `title` repeating the field's own name, `anyOf` of bare types where a
  type list says the same, and defaults on a reply nobody constructs. 22,6% of what the
  three servers announce in every turn, and not one field, type or `required` entry with
  it. This is the one file here that was **not** measured as a copy first — see
  `docs/architecture.md`, condition 1's second route.

## What it does not do

It does not know which upstream it is talking to, or which spec to cite in a refusal —
both travel as arguments (`upstream=`) or stay in the calling module's own prose. A caller
still owns its own `server.py`, `client.py`, `config.py` and error taxonomy: those were
measured at 8–58% identical across the three modules in `design.md`'s own table, which is
not a copy that drifted — it is three modules that differ because the things they call
differ.
