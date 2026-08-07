## 1. Scaffold

- [ ] 1.1 Create `modules/capital-gateway/` with `pyproject.toml` (Python ≥3.12, `uv`, `package = false`, ruff line-length 100, pytest `asyncio_mode = "auto"` and a `live` marker)
- [ ] 1.2 Add `.env.example` with `CAPITAL_API_KEY`, `CAPITAL_IDENTIFIER`, `CAPITAL_PASSWORD`, `CAPITAL_BASE_URL`, `CAPITAL_STREAM_URL`
- [ ] 1.3 Write `config.py`: pydantic settings plus the demo-only guard — a non-demo base or stream URL raises before the app is built
- [ ] 1.4 Write `errors.py` — the module's error type carrying an HTTP status
- [ ] 1.5 Test: a live host in either URL fails startup; missing credentials fail startup naming the absent value

## 2. Contract types

- [ ] 2.1 Write `dtos.py`: `AssetClass`, `Direction`, `Resolution`, `OrderStatus`, `OrderType`, `Instrument`, `InstrumentPage`, `Candle`, `Account`, `Position`, `Order`, `WorkingOrder`, `PlaceOrderRequest`, `UpdatePositionRequest`, `Capabilities` — carried over from `broker-gateway`, with `Capabilities` extended to state the environment and streaming
- [ ] 2.2 Add the deep-history response type: candles plus collected count, requests issued, covered period, and whether history ended before the request was satisfied
- [ ] 2.3 Validation: LIMIT/STOP without a level is rejected; an amendment naming neither stop is rejected

## 3. REST client and session

- [ ] 3.1 Write `client.py`: async httpx client, login capturing `CST` and `X-SECURITY-TOKEN`, authed request helper, one re-login and retry on 401
- [ ] 3.2 Share one in-flight login across concurrent callers so a burst causes a single login
- [ ] 3.3 Put every provider call behind one bounded gate that keeps the module under 10 req/s
- [ ] 3.4 Test with `respx`: expired session re-authenticates and retries once; concurrent callers trigger exactly one login; the gate bounds request concurrency

## 4. Mapping and adapter

- [ ] 4.1 Record provider payload fixtures under `tests/fixtures/` (session, accounts, markets search, market navigation, prices, positions, working orders, confirms)
- [ ] 4.2 Write `mapping.py` — pure payload→DTO functions, candles read from the **bid** side
- [ ] 4.3 Write `adapter.py`: accounts, active-account switch, instrument search, catalogue traversal with its own bound and a `truncated` flag, candle reads
- [ ] 4.4 Adapter: positions, order placement (MARKET → position, LIMIT/STOP → working order), close, amend with per-field tri-state, working-order list and cancel
- [ ] 4.5 Adapter: `dealReference → confirms` settlement, bounded attempts, unresolved reference returns `PENDING` and never `FILLED`
- [ ] 4.6 Test mapping against fixtures alone; test the adapter against `respx`, including a rejected deal and a settlement that never arrives

## 5. Deep history

- [ ] 5.1 Write `history.py`: backwards paging, window width `(count − 1) × resolution`, `from`/`to` as `YYYY-MM-DDTHH:MM:SS` UTC
- [ ] 5.2 Anchor each further window on the oldest candle collected, not on the clock
- [ ] 5.3 Stop on `error.prices.not-found`, on a window yielding nothing older, or on the requested count; sort, dedupe by timestamp, trim to the request
- [ ] 5.4 Stop issuing provider requests when the caller disconnects
- [ ] 5.5 Test: a multi-page read returns one ordered series with no duplicates; a run past the bottom of history returns what it collected and says history ended; a stalled window terminates the loop

## 6. Streaming

- [ ] 6.1 Write `stream/messages.py` — the published shapes for `candle`, `quote`, `status`, `error`
- [ ] 6.2 Write `stream/forming.py`: quotes → forming candle; floor the timestamp to the resolution intraday, extend the last known candle for `DAY`/`WEEK`, and let a settled candle overwrite the assembled one. No I/O
- [ ] 6.3 Write `stream/upstream.py`: one outbound connection per `(epic, resolution)`, both subscriptions (`OHLCMarketData` + `marketData`), tokens injected per message, ping inside the provider's tolerance, reconnect on drop while subscribers remain
- [ ] 6.4 Keep only `priceType: "bid"` from the closed-candle event so one candle is published per period
- [ ] 6.5 Write `stream/hub.py`: rooms keyed by `(epic, resolution)`, fan-out, connection opened on first subscriber and closed after the last one leaves
- [ ] 6.6 Test `forming.py` in isolation: first quote opens, later quotes extend high/low and move close, a new period opens a new candle, `DAY`/`WEEK` extend instead, a settled candle replaces the assembled one
- [ ] 6.7 Test the hub against a fake upstream: a second subscriber opens no second connection, the last leaver closes it, a drop publishes `reconnecting` and recovers

## 7. HTTP and WebSocket surface

- [ ] 7.1 Write `app.py`: lifespan owning the client and hub, error handler mapping the module's error type to a status, `/capabilities` stating provider, environment `demo`, streaming and order types
- [ ] 7.2 Routes: `/accounts`, `/accounts/active`, `/instruments`, `/instruments/search`, `/instruments/{symbol}/candles`, `/instruments/{symbol}/history`
- [ ] 7.3 Routes: `/positions`, `/orders`, `/positions/{id}` (close, amend), `/working-orders`, `/working-orders/{id}`
- [ ] 7.4 WebSocket `/ws/stream?symbol=&resolution=` — refuse a connection naming no symbol
- [ ] 7.5 Test: the published OpenAPI covers every route; a stream without a symbol is refused; no response or message carries a credential or provider token

## 8. Verification and documentation

- [ ] 8.1 Live smoke test behind `--run-live`: a session opens, a deep read pages, the stream delivers quotes and a settled candle
- [ ] 8.2 Run `ruff` and the full suite clean
- [ ] 8.3 Write the module README — what, run, test, contract — on one screen, including the WebSocket message shapes
- [ ] 8.4 Write the repository README and `docs/architecture.md` establishing the `modules/` layout
