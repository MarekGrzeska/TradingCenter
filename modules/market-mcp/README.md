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
- `upstream.py` — narrow pydantic models for the shapes this module actually reads off
  market-data's wire. Not `market_data.contract` — no shared library between modules.
- `reduce.py` — the one place aggregation and truncation happen: bucket a candle series
  down to a target count, or take the first N of a list, always saying what was cut.
- `uncertainty.py` — the sentences every candle/coverage tool builds from `uncovered`,
  `derived`, and an empty series, so the archive's own uncertainty reaches the model in
  the same words wherever it applies.
- `errors.py` — `ToolRefusal`, the one exception a tool raises to refuse a request; the
  MCP server turns it into `isError=True` with the message as content.
- `scripts/contract.py` — `generate`/`check` against market-data's own OpenAPI document,
  the same mechanism the terminal's `contract.mjs` uses.
- `contract/market-data.openapi.json` — the committed snapshot `tests/test_contract.py`
  checks every field this module reads against.
- `server.py` — builds the `FastMCP` instance and mounts `/health` on the same ASGI app
  the streamable-http transport serves, so the platform can probe it without an MCP
  session.
- `resources.py` — the resources (`market://pairs`, `market://indicators/catalogue`,
  `market://coverage/{symbol}/{resolution}`) and the `analyze-symbol` prompt.
- `tools/` — the tool surface, one file per concern (mirrors `market_data/routers/`):
  `pairs.py`, `candles.py`, `instruments.py`, `indicators.py`, plus `_shared.py` for
  what more than one of them needs (the window default, the read-only-empty-series
  distinction).
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

One file, `test_transport_parity.py`, spawns a real `python -m market_mcp stdio`
subprocess and binds a real port for the streamable-http transport — needs no running
market-data, but takes seconds rather than milliseconds. It runs in the default suite,
same as everything else; there is no flag for it.

Regenerating the contract snapshot after a `market-data` change:

```bash
uv run python scripts/contract.py generate   # rewrite contract/market-data.openapi.json
uv run python scripts/contract.py check      # fail if it is stale — what CI runs
```

Needs `market-data`'s own dependencies resolvable (`uv run --python 3.12` in that
module's directory) but no database, no gateway and no running server: the OpenAPI
document is a property of `market_data/contract.py`'s Pydantic models.

## Tools

| Tool | Answers | Reads |
|------|---------|-------|
| `list_tracked_pairs` | Which pairs the archive is collecting, and whether collection is happening — the first thing to check before asking about a symbol. | `GET /pairs` |
| `get_candles` | OHLC candles over a time range, aggregated to ~200 buckets above the ceiling, refused above ~2000. | `GET /candles/{symbol}` |
| `get_last_price` | The most recent candle, with its age — a price is not trustworthy without knowing how old it is. | `GET /candles/{symbol}` |
| `summarize_range` | A window's shape in a dozen numbers: change, choppiness, biggest move — instead of its candles. | `GET /candles/{symbol}` |
| `describe_coverage` | What the archive has actually verified for a pair, and how far back its history reaches. | `GET /coverage/{symbol}` |
| `search_instruments` | The symbol other tools expect, from a name a person would type. | `GET /instruments/search` |
| `list_indicators` | Every indicator the archive can compute, its parameters and their defaults — filterable by group. | `GET /indicators` (cached once per process) |
| `describe_indicator` | The full catalogue entry for one indicator — ranges, aliases, output shape, render hint. | `GET /indicators` (cached) |
| `compute_indicators` | Up to 10 named indicators on one shared axis. `mode="latest"`: value, slope, distance from price, bars since it crossed price. `mode="series"`: the window, thinned to ≤200 points. | `POST /indicators/{symbol}` |
| `levels_near_price` | Every level, zone and marker the catalogue can compute, merged and sorted by distance from the last price. | `POST /indicators/{symbol}` (batched, ≤10 per call) |

Every candle/coverage tool distinguishes three reasons for an empty answer — nobody
tracks the pair, the window is unverified, or the archive did not respond — instead of
letting a caller read silence as "the market was quiet"
(`specs/market-mcp-answers`). An indicator result carries the archive's own `error` text
verbatim, and an unsettled value says why — the warmup its formula needs, not
necessarily how much was missing (the archive does not publish that second number).

Also published: three resources (`market://pairs`, `market://indicators/catalogue`,
`market://coverage/{symbol}/{resolution}`) for a client that wants to read rather than
call, and one prompt, `analyze-symbol` — coverage, then a window summary, then
indicators, then naming what is still not known.

## Contract with market-data

This module does not import `market_data` — no shared library between modules, same rule
every module in this repository follows. What it reads is checked against a committed
OpenAPI snapshot (`contract/market-data.openapi.json`), the same mechanism the terminal
uses for its generated types. `tests/test_contract.py` asserts every field a tool or
resource reads is still published; regenerate the snapshot with `scripts/contract.py`.

## Reliability

- One retry on a 5xx from market-data — every request through `client.py` is a read, so
  retrying duplicates nothing.
- A timeout or an unreachable archive is a `ToolRefusal` naming the failure ("this is a
  problem on this module's side, not missing data"), never a raw exception a caller has
  to guess the meaning of.
- At most 8 requests to market-data in flight at once — a burst of concurrent tool calls
  is a burst of concurrent load on the archive, bounded here rather than left open.
- Every tool is marked `readOnlyHint=True` — a structural claim an MCP client can act on,
  not just a convention this module follows.

## MCP protocol version

SDK `mcp==1.27.0`, checked 2026-08-11. Pinned exactly, not a floor — `mcp` released `2.0.0`
during this module's first draft and moved `FastMCP` out of `mcp.server.fastmcp`, the same
kind of break `pyright` is pinned against in every other module here, from an SDK that
moves faster.
