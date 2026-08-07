# terminal

The operator-facing frontend. React + TypeScript + Vite, talking to `capital-gateway` over
HTTP and WebSocket. Under active implementation — this README grows with it.

## Findings

**`capital-gateway`'s REST `ts` carries an explicit UTC zone marker.** `mapping.py::_candle_ts`
appends `Z` whenever the provider's `snapshotTimeUTC` field is present — which is the field
every candle request in this module's testing has populated. `Date.parse` is therefore safe on
that path without guessing a timezone. The fallback (`snapshotTime`, the provider's unmarked
local time, used only when `snapshotTimeUTC` is absent) stays ambiguous by the gateway's own
design and is inherited as-is — see `src/data/time.ts`. Confirmed against source, to be
reconfirmed against a live response in task 8.2.
