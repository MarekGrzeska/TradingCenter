# market-mcp

Read-only MCP tools over `market-data`'s candle archive and indicator catalogue —
**reduced for a model, not proxied for a chart**. A day of MINUTE candles is ~1440 JSON
objects; a model asking "what happened this hour" does not need any of them individually,
it needs a summary. This module is that summary, not a pass-through.

**Every tool reads. None writes.** There is no configuration that adds a write tool —
starting collection on a pair or deleting one happens in the terminal, where the cost of
either is visible before it is clicked. See `docs/mcp-plan-wdrozenia.html` (repo root) for
the plan this module was built from, and
`openspec/changes/add-market-data-mcp/specs/market-mcp-tools/spec.md` for the requirement
that keeps it that way.

**Two transports, one tool surface**: `stdio` for a client on a desk (Claude Desktop,
`claude code`), streamable HTTP for the agent module calling across a network. Both are
built from the same `market_mcp/server.py`.

## What

- `config.py` — settings and the upstream mode switch: `MARKET_DATA_SCOPE` set means the
  archive is off this machine and a managed-identity token proves this module to it;
  unset means `MARKET_DATA_URL` must be loopback. A configuration leaving that ambiguous
  is refused at startup.
- `client.py` — the one seam every request to `market-data` passes through. A method
  other than `GET` is rejected before a socket opens; the one named exception is
  `POST /indicators/{symbol}`, a computation, not a write.
- `server.py` — builds the `FastMCP` instance and mounts `/health` on the same ASGI app
  the streamable-http transport serves, so the platform can probe it without an MCP
  session.
- `tools.py` — the tool surface. One function per tool, registered with `@mcp.tool()`.
- `__main__.py` — `python -m market_mcp [stdio|http]`, defaulting to `stdio`.

## Run

```bash
cp .env.example .env               # MARKET_DATA_URL — defaults to the local archive on :8020
uv run python -m market_mcp stdio  # for a desktop client
uv run python -m market_mcp http   # for the agent module, or for manual testing
```

Pointing `MARKET_DATA_URL` anywhere off loopback needs `MARKET_DATA_SCOPE` set too — see
`config.py`'s docstring.

### Trying it from Claude Desktop

```json
{
  "mcpServers": {
    "market-mcp": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/modules/market-mcp", "python", "-m", "market_mcp", "stdio"]
    }
  }
}
```

## Test

```bash
uv run pytest              # respx-mocked market-data; no network, no running instance
uv run pytest --run-live   # + tests against a real running market-data (not yet added)
uv run ruff check . && uv run ruff format --check .
uv run pyright             # types, over market_mcp/
```

## Tools

| Tool | Answers | Reads |
|------|---------|-------|
| `list_tracked_pairs` | Which pairs the archive is collecting, and whether collection is happening — the first thing to check before asking about a symbol. | `GET /pairs` |

Growing incrementally — see `openspec/changes/add-market-data-mcp/tasks.md` for the rest
of the surface (candles, coverage, indicators) and the reduction each one applies before
answering.

## Contract with market-data

This module does not import `market_data` — no shared library between modules, same rule
every module in this repository follows. What it reads is checked against a committed
OpenAPI snapshot (`contract/market-data.openapi.json`, added alongside the tools that need
it), the same mechanism the terminal uses for its generated types.

## MCP protocol version

SDK `mcp==1.27.0`, checked 2026-08-11. Pinned exactly, not a floor — `mcp` released `2.0.0`
during this module's first draft and moved `FastMCP` out of `mcp.server.fastmcp`, the same
kind of break `pyright` is pinned against in every other module here, from an SDK that
moves faster.
