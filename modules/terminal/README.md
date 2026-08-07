# terminal

The operator-facing frontend: charts, in a grid, fed by `capital-gateway`. React +
TypeScript, talking to the gateway over HTTP and WebSocket and depending on nothing else in
this repository.

## What

- `data/` — the contract and its implementations. `types.ts` (`Bar`, `Instrument`,
  `Resolution`), `source.ts` (the `MarketDataSource` interface every view reads through),
  `gatewaySource.ts` (the one implementation), `marketData.ts` (the single instance every
  view reads), `socketHub.ts` (one WebSocket per `symbol|resolution`, ref-counted), `merge.ts`
  (candles deduped by timestamp), `time.ts` (the ISO → epoch-seconds seam),
  `config.ts` (the two independent base addresses).
- `app/` — the shell: tab registry, routing, theme, connection indicator, per-view error
  boundary.
- `chart/` — the reusable candlestick chart, identical standalone and in a grid slot.
- `grid/` — six slots with fixed identities, layout presets, and persistence.
- `instruments/` — search and catalogue, feeding instruments into the active slot.

## Run

```bash
pnpm install
cp .env.example .env      # optional; the defaults already target the dev proxy
pnpm dev                  # http://localhost:5173
```

`capital-gateway` must be running on port 8010 — there is no offline mode, and without it the
terminal says the source is unreachable and draws nothing. From the repo root,
`./scripts/dev.ps1` starts the gateway, waits for it, then starts the terminal against it.

## Test

```bash
pnpm test        # vitest — data layer, shell, chart, grid, instruments
pnpm typecheck
pnpm lint
```

The chart's canvas is not assertable, so chart and grid tests stub the charting library
and assert what the component *asks it to draw*. What that cannot cover was checked by
driving a real browser against a real gateway — see Findings.

## Contract

This module consumes; it publishes nothing. It depends on `capital-gateway`:

| Direction | What |
|---|---|
| `GET /instruments/search?q=` | search results |
| `GET /instruments` | the catalogue, with its `truncated` flag |
| `GET /instruments/{symbol}/history` | candles |
| `GET /capabilities` | the reachability check behind the connection indicator |
| `WS /ws/stream?symbol=&resolution=` | live candles and quotes |

**The HTTP and WebSocket base addresses are configured separately** — `VITE_GATEWAY_HTTP`
and `VITE_GATEWAY_WS` — and each accepts a relative path or a full URL. This is not
redundancy: Azure Static Web Apps, the deployment target, proxies HTTP only and caps a
request at 45 s, so a topology where the stream goes straight to the gateway host while
static files come from elsewhere has to be configurable without touching code. Locally
both are relative and Vite's dev proxy carries them.

## Findings

Everything here was **measured**, not assumed.

**`ts` from the gateway's REST side carries an explicit `Z`.** Confirmed against a live
demo response: `{"ts":"2026-08-07T16:20:00Z", ...}`. `mapping.py::_candle_ts` appends it
whenever the provider's `snapshotTimeUTC` is present, which it was on every request made
here. `Date.parse` is therefore unambiguous on that path. The fallback — unmarked
provider-local `snapshotTime`, used only when the UTC field is absent — stays ambiguous by
the gateway's own design and is inherited as-is rather than papered over.

**The forming candle really does move the chart.** Watched on US100 `MINUTE_5` against the
demo account: the last candle's OHLC changed within 45 s, with no settled candle in
between. That is the behaviour the gateway assembles it for — `ohlc.event` fired 0 times in
60 s in its own measurements.

**A 3x2 of six distinct pairs holds exactly six connections.** Measured in the browser:
six concurrent sockets, peak six, one per pair. Two additional sockets appear in the log
and close in the same tenth of a second — React's `StrictMode` double-invokes effects in
development, so a freshly mounted chart subscribes, unsubscribes and resubscribes. They are
never concurrent, and a production build does not double-invoke at all. Dropping from 3x2
to 2x2 closes the vanished slots' sockets.

**Live bars normally arrive before the history read finishes.** The subscription opens
immediately while a 500-bar read takes seconds, so history is *merged* under whatever the
stream already delivered rather than replacing it — otherwise the forming candle would
vanish until the next tick, which at `DAY` resolution could be hours.

**Changing what a chart points at has to clear it, not just re-read it.** Caught in the
browser back when a second source existed: the previous source's prices stayed on screen
under the new source's label for the seconds a deep read takes. Not a stale chart — a wrong
one. The series is cleared whenever the symbol, the resolution *or* the source instance
changes, which is what keeps that true when the candle store becomes the second
implementation.

**Up candles are drawn hollow.** Teal-vs-red passes every gate in the palette validator
except protan CVD separation (ΔE 6.5, inside the 6–8 floor band), which is only legal
alongside a non-colour encoding. Body fill is that encoding, and it survives greyscale too.

**Streamed candles carry no volume**, so the readout shows `n/a` rather than `0` — the
gateway's `volume: null` means "not reported", and zero would be a claim about the market.
Volume appears on candles read from history.
