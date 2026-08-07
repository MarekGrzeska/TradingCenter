## Why

Two throwaway spikes proved the two halves of capital.com separately and neither can be
used by anything else. `TradingHub/modules/broker-gateway` (Python/FastAPI) trades but
declares `has_streaming: false` and fetches at most 1000 candles. `TwelveDataTest`
(Vite dev-server plugin) streams live candles and pages history 20 000 bars deep, but its
knowledge lives in a React hook and a Vite plugin — reachable only from a browser tab, and
only while the dev server runs.

TradingCenter is the successor ecosystem to TradingHub. Its first module folds both spikes
into one standalone service so that trading, deep history and a live feed come from a single
contract that an agent, a backtest or a future React console can all consume.

## What Changes

- New module `modules/capital-gateway` — FastAPI service, the only place that knows
  capital.com exists.
- **Trading**, carried over from `broker-gateway`: accounts, active-account switch,
  positions, MARKET/LIMIT/STOP orders, attached SL/TP, position amendment, working orders,
  and the async `dealReference → confirms` settlement.
- **Deep history**, carried over from the `TwelveDataTest` spike: candles paged backwards
  past the provider's 1000-row ceiling, anchored on the oldest bar already collected rather
  than on the clock.
- **Live streaming**, new as a published contract: an outbound WebSocket for consumers
  carrying `candle` (forming and settled) and `quote`. One upstream connection per
  `(epic, resolution)` is shared by every subscriber.
- **The forming candle is assembled server-side**, not by the consumer. Bucketing quotes into
  the candle in progress moves out of the React hook it lives in today, so every consumer sees
  one definition of "the current candle".
- **Demo only.** A base URL that is not the demo host is refused at startup. This module
  cannot place an order with real money.
- **`BrokerPort` is deleted, neutral DTOs are kept.** The DTOs are the HTTP contract. The
  Protocol is referenced by nothing executable in `broker-gateway` today — `app.py` types its
  dependency as the concrete adapter — so it enforces nothing it appears to enforce.
- **No storage.** History is paged from the provider per request; nothing is persisted.

## Capabilities

### New Capabilities
- `capital-session`: authentication against capital.com, session lifetime and renewal, the
  demo-only guard, accounts and active-account selection, published capabilities.
- `capital-market-data`: instrument search and enumeration, candle reads, and history paged
  deeper than one provider request.
- `capital-trading`: positions, order placement across MARKET/LIMIT/STOP, attached and amended
  stops, working orders, and how an asynchronous deal becomes a settled result.
- `capital-streaming`: the outbound WebSocket contract — message kinds, the forming candle,
  subscription sharing, liveness and reconnection.

### Modified Capabilities

None — TradingCenter has no specs yet.

## Impact

- **New**: `modules/capital-gateway/` (Python 3.12, FastAPI, httpx, websockets, pydantic;
  `uv` + `ruff` + `pytest`). Repository layout `modules/`, `openspec/`, `docs/` is established
  by this change.
- **Contract**: HTTP described by OpenAPI at `/docs`, plus a WebSocket at `/ws/stream` whose
  message shapes are published as JSON Schema — OpenAPI does not describe WebSocket payloads.
- **Credentials**: `CAPITAL_API_KEY`, `CAPITAL_IDENTIFIER`, `CAPITAL_PASSWORD` in `.env`,
  never leaving the process.
- **Not affected**: TradingHub keeps running untouched. `broker-gateway` there is superseded
  by this module, but retiring it is a separate decision, not part of this change.
- **Deliberately absent**: no database, no scheduler, no UI, no live-account access, no
  provider abstraction layer.
