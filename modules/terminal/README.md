# terminal

The operator-facing frontend: charts, in a grid, fed by `market-data` and `capital-gateway`.
React + TypeScript, talking to both over HTTP and WebSocket and depending on nothing else in
this repository.

**Two back ends, one interface.** Candles and the live stream come from `market-data`, the
archive, which has yesterday's as well as today's. The instrument catalogue stays with
`capital-gateway`, which owns it. Views see one `MarketDataSource` and never learn which
call went where — the composition is `marketData.ts` and nothing else.

**Nothing is archived because somebody looked at a chart.** Collecting a pair holds a
provider connection open around the clock and the provider limits how many a session may
hold, so what gets collected is a standing decision — made, and taken back, on the Archive
tab.

## What

- `data/` — the contract and its implementations. `types.ts` (`Bar`, `Instrument`,
  `Resolution`), `source.ts` (the `MarketDataSource` interface every view reads through),
  `archive.ts` (candles and the subscription), `gatewaySource.ts` (the catalogue),
  `marketData.ts` (the single instance every view reads, composed from the two),
  `socketHub.ts` (one WebSocket per `symbol|resolution`, ref-counted), `merge.ts`
  (candles deduped by timestamp), `time.ts` (the ISO → epoch-seconds seam), `http.ts`
  (a failed request turned into something an operator can read), `config.ts` (the base
  addresses).
- `app/` — the shell: tab registry, routing, theme, connection indicator, per-view error
  boundary.
- `chart/` — the reusable candlestick chart, identical standalone and in a grid slot.
- `grid/` — six slots with fixed identities, layout presets, and persistence.
- `instruments/` — search and catalogue, feeding instruments into the active slot.
- `archive/` — the panel where the operator decides what `market-data` collects, and sees
  whether collection is actually happening.

## Run

```bash
pnpm install
cp .env.example .env      # optional; the defaults already target the dev proxy
pnpm dev                  # http://localhost:5173
```

`market-data` must be running on port 8020 and `capital-gateway` on 8010 — there is no
offline mode. Either being down is survivable and says so: without the archive the charts
report that candles are stale, without the gateway the instrument search stops. From the
repo root, `./scripts/dev.ps1` starts the gateway, waits for it, then starts the terminal
against it; the archive is started separately (see `modules/market-data/README.md`).

## Test

```bash
pnpm test        # vitest — data layer, shell, chart, grid, instruments, archive panel
pnpm typecheck
pnpm lint
```

The chart's canvas is not assertable, so chart and grid tests stub the charting library
and assert what the component *asks it to draw*. What that cannot cover was checked by
driving a real browser against the real back ends — see Findings.

## Contract

This module consumes; it publishes nothing.

From `market-data` — everything about candles:

| Direction | What |
|---|---|
| `WS /ws/candles?symbol=&resolution=` | the series as a snapshot, then every change |
| `GET /candles/{symbol}?resolution=&from=&to=` | a range read, with what was never collected marked |
| `GET /coverage/{symbol}?resolution=` | how far the archive reaches for a pair |
| `GET /pairs`, `POST /pairs`, `DELETE /pairs/{symbol}` | what is collected, as the operator decides it |
| `GET /health` | the reachability check behind the connection indicator |

From `capital-gateway` — the catalogue, which is its:

| Direction | What |
|---|---|
| `GET /instruments/search?q=` | search results |
| `GET /instruments` | the catalogue, with its `truncated` flag |
| `GET /capabilities` | its own reachability check |

**The archive's HTTP and WebSocket base addresses are configured separately** —
`VITE_ARCHIVE_HTTP` and `VITE_ARCHIVE_WS` — and each accepts a relative path or a full URL.
This is not redundancy: Azure Static Web Apps, the deployment target, proxies HTTP only and
caps a request at 45 s, so a topology where the stream goes straight to the archive host
while static files come from elsewhere has to be configurable without touching code.
Locally both are relative and Vite's dev proxy carries them. The gateway needs no WebSocket
address any more: the terminal reads its catalogue and nothing else.

**A relative prefix must not be a tab's route.** The archive answers on `/archive-api`, not
`/archive`, because `/archive` is the Archive tab — and a back end holding that prefix
shadows the tab for every request that reaches a server, which is a reload or a bookmark but
never a click. A test compares the two lists so the next prefix cannot repeat it.

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

**There is no history read left to race.** Live bars used to arrive before a 500-bar read
finished, which is why history is *merged* under whatever the stream already delivered
rather than replacing it. The archive's subscription opens with the series itself, taken
while its room is held still, so the race is gone — and the merge stays, because it costs
nothing and is what makes a reconnect's fresh snapshot fold into what is drawn instead of
blanking it.

**Changing what a chart points at has to clear it, not just re-read it.** Caught in the
browser back when a second source existed: the previous source's prices stayed on screen
under the new source's label for the seconds a deep read takes. Not a stale chart — a wrong
one. The series is cleared whenever the symbol, the resolution *or* the source instance
changes, which is what kept it true when the archive became the source of candles.

**Up candles are drawn hollow.** Teal-vs-red passes every gate in the palette validator
except protan CVD separation (ΔE 6.5, inside the 6–8 floor band), which is only legal
alongside a non-colour encoding. Body fill is that encoding, and it survives greyscale too.

**A candle can arrive without a volume**, so the readout shows `n/a` rather than `0` — a
`volume: null` means "not reported", and zero would be a claim about the market. It is the
period still being built that usually lacks one: the gateway assembles it from quotes,
which carry no size.
