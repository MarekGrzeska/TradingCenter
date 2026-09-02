# terminal

The operator-facing frontend: charts in a grid, the agent and its teams, the demo account,
and the prediction markets. React + TypeScript, talking to four back ends over HTTP and
WebSocket and depending on nothing else in this repository.

**Two of them behind one interface, and that is the market half only.** Candles and the
live stream come from `market-data`, the archive, which has yesterday's as well as today's.
The instrument catalogue stays with `capital-gateway`, which owns it. Views see one
`MarketDataSource` and never learn which call went where — the composition is
`marketData.ts` and nothing else. The workbench and `polymarket-data` are not behind it and
should not be: a conversation and a probability series share no shape with a candle.

**Nothing is archived because somebody looked at a chart.** Collecting a pair holds a
provider connection open around the clock and the provider limits how many a session may
hold, so what gets collected is a standing decision — made on the `Instruments` tab. It
runs the other way too: a chart slot only offers instruments the archive already
collects, because a chart of a pair nobody collects has nothing to draw.

**The Polymarket tab is where prediction markets are watched**, and the only place in this
system that can remove what was collected for one. Nine tools reach that module and three
of them write, but what they write is the watch list — no tool deletes a sample. That makes
this tab the capability's only door, and the irreversibility is sharper than the archive's:
Polymarket does not give back the history of a market that has resolved.

**Deleting a pair removes its data — irreversibly.** There is no "stop but keep the
candles" left in the terminal; `Instruments`' Delete stops collection and takes the data
with it, in one confirmed step that says so plainly before it happens. What it removed is
what makes a re-add later start from nothing rather than quietly inheriting a shorter
range it was never given, and it stays visible afterwards as an entry in `Data History`.

**Tabs.** `Graph` is the grid of charts. `Teams` is where a team of agents is composed —
roles and the dependencies between them, drawn rather than listed, because the
dependencies are what decide who sees whose work. `Instruments` is the one place that says what is
archived — one row per instrument, every resolution of it in one column, and since when
there is data for it: one date when the resolutions agree, split per resolution when they
reach differently far back — and where an
instrument is added, through a wizard that prices the work before starting it. `Data
History` is where that work is watched: what was pulled, how far a running pull has got,
where a failed one is retried, and — in the same timeline — every deletion that has
happened. Newest first, whatever the instrument: the tab is asked "what just happened"
before it is asked anything else.

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
- `ui/` — `Autocomplete`, the one search-as-you-type picker the terminal uses, plus the two
  sources it is given (asset classes, instruments in a class) and the
  debounce-and-stale-guard hook underneath it; and `ConfirmDialog`, the one way the terminal
  asks for consent. Every question that precedes something irreversible goes through it —
  never a row glued under a table — and it owns the work in flight, the second click, the
  failure that has to stay with its decision, `Escape` and the focus trap.
- `chart/` — the reusable candlestick chart, identical standalone and in a grid slot. The
  live edge comes from the subscription's snapshot; panning left pages older candles in from
  the archive's range endpoint (`useOlderBars.ts`), which never reads anything newer than the
  oldest candle already drawn and keeps paging until the viewport has a margin of candles to
  its left again. The price marked on the right-hand scale is the chart's own: the library's
  label reads the last *visible* bar, which in a chart panned into history is not the price
  anyone means.
- `grid/` — six slots with fixed identities, layout presets, and persistence. A slot's
  symbol is picked from a plain list of what the archive collects — the grid reads `/pairs`
  once for all six — and its resolutions from what that instrument is archived in.
- `instruments/` — the `Instruments` tab: what is archived, per instrument, and the wizard
  and acceptance dialog that add to it; Delete, which removes a pair's data with it.
- `history/` — the `Data History` tab: collection jobs per instrument and resolution, their
  measured progress and how long since anything last happened in them, and every deletion,
  in one timeline with the jobs, ordered newest first. A row opens the job it came from as a
  whole — every pair, every failure, and the one Retry, which covers the whole job because
  that is what it has always done.
- `teams/` — the `Teams` tab: the catalogue of operator-defined teams, and one team open on
  a canvas (`@xyflow/react`) as its agents and the dependencies between them. Like the
  agent's client since P8, this module's client (`teamsApi.ts`) is built on types
  generated from its own OpenAPI document — its surface is graphs and revisions, wide
  enough that a renamed field would arrive as `undefined` rather than as a compile error.
  Both pickers in the agent panel are built from what the module publishes: the model
  catalogue, and whatever its tool server announces. No model id and no tool name is
  written down here, and a test reads the source to keep it that way. A run is started
  from the catalogue and watched on that same canvas — each agent carrying the state of
  its step, its output and what it called — over the module's server-sent progress
  (`runs.ts`, `useRunMonitor.ts`). The graph a run is watched on is *its* revision, read
  by the id the run names; leaving the view drops the stream and nothing else, and the
  catalogue's run list is the way back in.

## Run

```bash
pnpm install
cp .env.example .env      # optional; the defaults already target the dev proxy
pnpm dev                  # http://localhost:5173
```

`market-data` must be running on port 8020 and `capital-gateway` on 8010 — there is no
offline mode. `agent` (8030) and `teams` (8050) are optional in the same sense every
back end here is: their tabs report what is unreachable rather than the app failing to
start. Either being down is survivable and says so: without the archive the charts
report that candles are stale, without the gateway the instrument search stops. From the
repo root, `./scripts/dev.ps1` starts the gateway, waits for it, then starts the terminal
against it; the archive is started separately (see `modules/market-data/README.md`).

## Test

```bash
pnpm test            # vitest — data layer, shell, autocomplete, chart, grid, instruments, history
pnpm typecheck
pnpm lint
pnpm contract:check  # fails when either generated contract (market-data, teams) is stale
```

All four run on every pull request (`.github/workflows/checks.yml`). The `pnpm` version is
pinned in `package.json`'s `packageManager`, so CI and a developer use the same one instead
of it being knowledge somebody has to be told.

The chart's canvas is not assertable, so chart and grid tests stub the charting library
and assert what the component *asks it to draw*. What that cannot cover was checked by
driving a real browser against the real back ends — see Findings.

## Deployed routing

`public/staticwebapp.config.json` tells Azure Static Web Apps to answer any address it
has no file for with `index.html`, and the router takes it from there. Without it **every
address except `/` is a 404** — a reload, a bookmarked tab, or anything that navigates for
real rather than through the router.

That was true from the day this was first deployed and nobody noticed, because clicking
between tabs never asks a server anything. Signing in is what surfaced it: MSAL returns
the operator to the address they started from, as a full navigation, and that address is a
tab.

It lives in `public/` because the deploy uploads `dist/` and that is what Vite copies
there. `/assets/*` is excluded, so a genuinely missing bundle stays a 404 rather than
being answered with an HTML page the browser would try to run as JavaScript.

## Signing in

Deployed, the terminal and `market-data` sit on two different hostnames, so the cookie
Easy Auth would rather use never leaves the browser. The terminal holds an **Entra token**
instead (`src/auth/`), and the shared HTTP client attaches it to every request — no
adapter and no route mentions it, which is what stops a route added later from quietly
going out bare.

**One token per back end, not one for the terminal.** Each of the four stands behind its
own gate and accepts a token minted for its own audience, so `src/auth/entra.ts` hands out
an `Identity` per audience off one MSAL session: same account, same state, one operator
signed in. Until 22 August 2026 there was a single token with market-data's audience,
presented to all three back ends, and the gateway had been *configured to accept it* — the
pre-authorizations for asking by name had been standing unused in `infra/entra.tf` since
August. A back end whose scope is unset is called with no credential and refuses, which a
tab can name; it is deliberately not given somebody else's token.

The candle stream cannot carry a header at all: the browser's WebSocket API has nowhere to
put one. So before every handshake — including every retry after a drop — the terminal asks
the archive for a **one-time ticket** and puts that in the address. The token never goes
near a URL; a ticket that leaks out of a log has already been spent.

Three states, not two. `unconfigured` is what a local run has: no `VITE_ENTRA_*`, no
credential attached, nobody asked to sign in, and no sign-in indicator in the top bar.
Being signed *out* is a different thing, shown as itself — an expired session and an
unreachable archive empty the same screen, and only one of them is fixed from here.

With identity configured, a signed-out terminal **sends itself to sign in**, once per page
load, before anything is rendered: nothing is visible without a token, so waiting for the
operator to find the button asks them to guess the only move there is. Exactly once —
`sessionStorage` carries a marker written before the page leaves, so a return that is still
signed out stops there and leaves it to the button in the top bar. A redirect loop is the
one failure an operator cannot click their way out of.

**If sign-in fails with an account you expect to work**, check which account. A guest
(B2B) account signs in under a different UPN than its own address — the same trap
documented for DBeaver in `docs/dbeaver-azure-connection.html`.

## Contract

This module consumes; it publishes nothing.

**The wire types are generated, not copied.** `src/data/contract.generated.ts` comes from
`market-data`'s own OpenAPI document — including the subscription's `Snapshot` and
`CandleChange`, which have no HTTP path and are published as components on purpose. The
thirteen hand-written `Raw*` interfaces in `archive.ts` are now one-line aliases into it.

```bash
pnpm contract:generate   # after a model changes in market-data's contract.py
pnpm contract:check      # fails if the committed file is stale
```

Regenerating needs no running server: the document is printed straight from the Python
models (`uv run python -m market_data.openapi`). That is deliberate — a check that needs a
live stack is a check nobody runs, which is how the two copies of this contract drifted
apart before it existed. A renamed field now stops this module compiling, on the line that
reads it, instead of arriving as `undefined` and showing up as a blank cell.

The `map*` functions stay hand-written. They are not transcription: they turn ISO strings
into epoch seconds, which is what keeps one timestamp spelling across the module.

Six sources since P8: market-data, the workbench's two surfaces (`teams.openapi`,
`agent.openapi`), polymarket-data, social-data and strategy. The conversation's was the
last hand-written one, and the one seam `contract:check` could not see drift across; its
event stream (`stream.ts`) stays hand-written, because OpenAPI does not describe SSE.

From `market-data` — everything about candles:

| Direction | What |
|---|---|
| `WS /ws/candles?symbol=&resolution=` | the series as a snapshot, then every change |
| `GET /candles/{symbol}?resolution=&from=&to=` | a range read, with what was never collected marked |
| `GET /coverage/{symbol}?resolution=` | how far the archive reaches for a pair |
| `GET /pairs`, `POST /pairs`, `DELETE /pairs/{symbol}` | what is collected, as the operator decides it |
| `POST /jobs/estimate` | what a prospective pull would cost, before anything is created |
| `GET /jobs`, `GET /jobs/{id}` | collection jobs and their progress, per pair |
| `POST /jobs/{id}/retry` | re-run only the chunks that failed |
| `GET /health` | the reachability check behind the connection indicator |

From `capital-gateway` — the catalogue, which is its:

| Direction | What |
|---|---|
| `GET /instruments/search?q=` | search results |
| `GET /instruments?asset_class=` | the catalogue, or one class of it, with its `truncated` flag |
| `GET /asset-classes` | the classes it describes instruments with |
| `GET /capabilities` | its own reachability check |

**The archive's HTTP and WebSocket base addresses are configured separately** —
`VITE_ARCHIVE_HTTP` and `VITE_ARCHIVE_WS` — and each accepts a relative path or a full URL.
This is not redundancy: Azure Static Web Apps, the deployment target, proxies HTTP only and
caps a request at 45 s, so a topology where the stream goes straight to the archive host
while static files come from elsewhere has to be configurable without touching code.
Locally both are relative and Vite's dev proxy carries them. The gateway needs no WebSocket
address any more: the terminal reads its catalogue and nothing else.

**A relative prefix must not be a tab's route.** The archive answers on `/archive-api`, not
`/archive`, which back then was a tab's route — a back end holding a prefix a tab also claims
shadows that tab for every request that reaches a server, which is a reload or a bookmark but
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
