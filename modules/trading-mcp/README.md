# trading-mcp

MCP tools over `capital-gateway`'s demo account — account reads and order writes,
so a `teams` zespół can act on what it decides rather than only recommend it. See
`openspec/changes/add-trading-tools/` for the proposal this module was built from.

**Every write tool is demo-only, checked against the gateway, not against this
module's own configuration.** `market-mcp` stays read-only to the letter — this is a
sixth module, not a switch flipped on the fifth one (specs/market-mcp-tools).

**One transport: streamable HTTP.** No `stdio` — a locally spawned process carries no
caller identity, and a module that moves money needs its `allowed_applications` list
to mean something (specs/trading-mcp-transport).

## What

- `config.py` — settings, and the one credential this module cannot start without:
  `capital-gateway`'s caller key, required at every address including loopback (the
  gateway's own `RequireGatewayKey` checks every caller the same way, unlike
  `market-data`'s Easy Auth, which only gates a remote instance).
- `client.py` — the one seam every call to the gateway passes through. Reads retry
  once on a `5xx`; writes never retry, because the gateway takes no idempotency key.
  Also the demo-only guard: `ensure_demo_environment()` reads `GET /capabilities` and
  refuses to proceed unless it names `"demo"`, re-checked after any failed call.
- `errors.py` — `GatewayUnavailable`, `GatewayRefused` and `NotDemoEnvironment`, the
  three ways a call to the gateway can fail, kept apart because only one of them is
  worth retrying and only one of them is this module's own guard rather than the
  gateway's answer.
- `network_identity.py` — a deliberate twin of `market_mcp`'s file of the same name:
  who may reach this module over the network, and the one exempt path (`/health`).
- `server.py` / `__main__.py` — the FastMCP instance and its one transport.
- `tools/account.py` — `get_positions`, `get_working_orders`, `get_balance`: reads,
  annotated `readOnlyHint=True`.
- `tools/orders.py` — `place_order`, `close_position`, `amend_stops`,
  `cancel_working_order`: writes, annotated as changing state. Every one re-checks
  the demo environment before touching the gateway and is never retried by this
  module on its own failure.
- `tools/_shared.py` — the two seams every tool goes through: `_read` and `_write`,
  which turn a `GatewayClient` outcome into a refusal, an access failure, or a
  settled/unsettled `OrderResultOut`. A provider `REJECTED` is a refusal naming the
  reason; a `PENDING` settlement is `outcome="unsettled"`, carried through rather
  than resolved.

## Running

```bash
uv run python -m trading_mcp
```

Needs `capital-gateway` running and reachable, and `CAPITAL_GATEWAY_API_KEY` set to
its `GATEWAY_API_KEY`. Copy `.env.example` to `.env` first.

```bash
uv run pytest
uv run ruff check .
uv run pyright
```
