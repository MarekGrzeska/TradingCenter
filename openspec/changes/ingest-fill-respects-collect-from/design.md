## Context

Proposal.md, „Why" has the incident. Here: only what shapes the fix.

Two independent mechanisms reach back for a newly tracked pair's history, and neither knows the
other exists:

- **The job system** (`jobs/plan.py`, `jobs/runner.py`) — created only when the wizard's dialog is
  accepted, plans chunks explicitly bounded to `collect_from`, and is what the operator actually
  priced and confirmed.
- **The quiet fill** (`ingest/backfill.py`'s `fill_gap`, called from `ingest/live.py`'s
  `PairIngest._close_gap`) — runs automatically every time `PairIngest.run()` starts, which is
  every time `Ingest.sync()` picks up a newly tracked pair (`app.py`'s `POST /pairs` calls `sync()`
  right after tracking, in the same request that also creates the job). It exists for the plain,
  no-wizard case — a pair tracked by a bare `POST /pairs {symbol, resolution}` has no job and
  nothing else would ever backfill it — but it runs unconditionally, including when a job already
  exists for the same pair.

`bars_to_close_gap` decides how many candles to ask for. For a pair with `latest_candle is None`
(nothing collected yet) it returns `min(default_bars, MAX_BARS_PER_FILL)` — a fixed count from
`Settings.default_backfill_bars`, module-wide, with no idea what `collect_from` this particular
pair was tracked with.

`collect_from` itself is never absent: `track()` always sets it, defaulting to
`default_collect_from(resolution, default_bars, now)` — the same depth this bug hands out — when
the caller does not give one. So the fixed-depth behavior was, and remains, correct for a pair
tracked without an explicit date. The bug is narrower: a pair tracked *with* an explicit,
shallower `collect_from` still gets the deep fixed-depth fill anyway, because nothing downstream
of `track()` looks at the value it just stored.

## Goals / Non-Goals

**Goals:**

- The quiet fill for a pair with nothing collected MUST NOT write a candle older than that pair's
  `collect_from`.
- A pair tracked without an explicit `collect_from` keeps behaving exactly as it does today —
  this is a correctness fix for one case, not a behavior change for the common one.

**Non-Goals:**

- Coordinating the quiet fill with the job system so they stop doing redundant work for a pair
  both are backfilling. Once the fill is clamped to `collect_from`, running both is wasted
  provider requests, not wrong data — `write_candles` already dedupes by `(symbol, resolution,
  period_start)` and `record_coverage` already merges ranges, so the overlap is inert. Teaching
  the fill to check job state crosses into the job system's domain for a savings that is provider
  requests, not correctness, and belongs in its own change if it is ever worth the coupling.
- Anything about a pair that already has candles (`latest_candle is not None`). That branch of
  `bars_to_close_gap` only ever asks for what is *missing since the last candle*, which cannot run
  past `collect_from` in the first place — the bug is specific to the "nothing collected yet"
  branch.
- Retroactively touching data this bug already collected. Real provider data, just fetched
  without being asked — proposal.md, Impact.

## Decisions

### `bars_to_close_gap` gains a `collect_from` parameter and clamps the "nothing yet" branch

```python
def bars_to_close_gap(
    resolution: Resolution,
    latest_candle: datetime | None,
    now: datetime,
    default_bars: int,
    collect_from: datetime,
) -> int:
    if latest_candle is None:
        return min(default_bars, MAX_BARS_PER_FILL, periods_between(resolution, collect_from, now))
    ...
```

`collect_from` becomes required, not optional-with-a-None-fallback: every tracked pair has one by
construction (`track()` guarantees it), so a caller with no value to pass is a caller with a bug
worth surfacing as a `TypeError`, not one worth silently reverting to the old, wrong depth.

### `periods_between` moves from `jobs/plan.py` to `periods.py`

`ingest/backfill.py` needs a "how many bars fit between these two moments" count, and
`jobs/plan.py` already has exactly that function — but `jobs/plan.py` imports `MAX_BARS_PER_FILL`
*from* `ingest/backfill.py`, so `backfill.py` importing `periods_between` back from `jobs/plan.py`
would be a cycle. `periods.py` is the neutral home both already sit next to (`period_length` is
already there, and neither module imports the other through it): move `periods_between` there,
update its two existing call sites (`jobs/plan.py`, `jobs/runner.py`) and the test file that
imports it, rather than leaving a re-export behind for call sites this same change is already
touching.

### `fill_gap` reads `collect_from` itself, in the same connection it already acquires

`fill_gap` already does `async with pool.acquire() as conn: latest = await read_latest_period(...)`
before deciding how many bars to ask for. It reads `collect_from` in the same block, via a new
`tracking.read_collect_from(conn, symbol, resolution) -> datetime | None` — one more query on a
connection already open, not a second round trip.

`None` (pair not found) is treated as "nothing to fetch", not as "fall back to the old unclamped
depth". By the time `fill_gap` runs, `PairIngest.run()` has already checked `still_tracked()`, so
`None` here means the pair was untracked in the narrow window between that check and this query —
the same shape of race `delete-archived-pair-data`'s `execute_chunk` guard closes on the job side,
and it gets the same answer: a pair nobody is tracking anymore gets nothing written for it, never
a deep fetch nobody asked for.

## Risks / Trade-offs

- **`periods_between` rounds up (`math.ceil`)** — so a clamped fill can overshoot `collect_from` by
  up to just under one period, and the fetched window can start slightly before it. This is the
  same rounding the job system already accepts for its own chunk sizing (`periods_between`'s own
  docstring: "a safe overestimate rather than a guess that could come in short"), and one period's
  width is immaterial next to the bug this fixes (years, not minutes).
- **`MAX_BARS_PER_FILL` can still cut a fill short of `collect_from`** in one pass — a pair whose
  `collect_from` is deeper than 50,000 bars away needs more than one fill to reach it. This is
  already true today for `default_bars` itself and is not something this change makes worse; the
  job system is the mechanism built to walk a deep range in windows, and a pair added through the
  wizard already gets one.
- **Moving `periods_between`** touches two existing call sites and a test file's imports —
  mechanical, but a real diff outside `ingest/`. Named here so it does not read as scope creep
  when it shows up in the tasks.

## Migration Plan

No schema change, no data migration. Purely a change in what the next fill for a pair with
nothing collected asks for; a pair whose fill already ran under the old behavior is unaffected
until it is untracked and tracked again (or deleted and re-added).
