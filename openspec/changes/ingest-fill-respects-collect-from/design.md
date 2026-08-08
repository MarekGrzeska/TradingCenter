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

### What clamping the fill did not fix

The live retest after that fix still showed data reaching months before the requested date, on the
job path this time. Row counts in `candles` matched `collection_job_chunks.candles_written` exactly,
which rules the quiet fill out: the job wrote them.

`bars` and `periods_between` are not the same quantity. `execute_chunk` sizes its request as
`periods_between(resolution, chunk_start, chunk_end)` — **calendar periods** in the window — and
the gateway pages until it holds that many **candles**. US100 trades roughly 70% of calendar time,
so a chunk asking for a January-to-August window's worth of periods keeps paging past January until
it has counted out the missing 30%, and lands in the previous autumn. No count fixes this, because
the ratio is a property of the instrument's session calendar, which neither module knows. The older
edge has to be said as a moment.

### What saying it as a moment then exposed

Once the gateway had a floor, its last window became narrow and clamped to it. Capital answers such
a window with `error.prices.not-found`, or with the same candle it already returned — and `collect`
read both as "the provider has nothing older". That claim is not local: `execute_chunk` records it
as the pair's permanent boundary and calls `skip_chunks_beyond_history`, settling every older chunk
still queued with zero requests and no retry, since nothing failed.

Measured twice, through the two different ways `collect`'s loop can run out — the empty-window
branch, then the no-progress branch, which the first fix did not touch. Second time in the
database:

```
MINUTE_5  done     2026-02-16 07:01 → 2026-08-08 21:41   35329 candles, 52 requests
MINUTE_5  skipped  2026-01-01 00:00 → 2026-02-16 07:01       0 candles,  0 requests
```

The job reported `done`. Six weeks the operator asked for were never fetched.

## Goals / Non-Goals

**Goals:**

- The quiet fill for a pair with nothing collected MUST NOT write a candle older than that pair's
  `collect_from`.
- A pair tracked without an explicit `collect_from` keeps behaving exactly as it does today —
  this is a correctness fix for one case, not a behavior change for the common one.
- A chunk MUST NOT store a candle older than its own window, whatever the gateway returns.
- Reaching a caller-supplied floor MUST NOT be reported as the provider's history ending, by any
  route out of the paging loop.

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

### The gateway takes an `after` floor, and both callers pass it

`GET /history` gains `after`, alongside the existing `before` anchor, and `collect` uses it three
ways: windows are clamped to it (`window_before(..., floor=after)`), so no request is spent on
candles that would be discarded; paging stops once a page reaches it; and anything older that still
arrives inside a page is dropped before the answer is built. The last one is not redundant with the
first — a page is only ever clamped at its *edges*, and Capital returns whole candles, so the
oldest one in a clamped window can still start before the floor.

The alternative considered was to leave the gateway alone and filter in `market-data` only. Rejected
because a request whose window reaches years past what the caller wants still *costs* those
requests, and because the same overshoot would be re-derived by every future consumer of `/history`.

Both `market-data` callers pass it — `after=chunk.chunk_start` from `execute_chunk`,
`after=collect_from` from `fill_gap` — **and** filter what came back before writing. Belt and
braces on purpose: what the archive stores is this module's promise, and a promise kept by asking
someone else nicely is not kept. The filter is also what makes the minute-rollup refresh safe, since
refreshing over candles that were dropped would derive a bucket from a source that was never stored.

### Reaching the floor is not `history_ended`, decided in one place

`collect` keeps two separate flags. `history_ended` means the provider has nothing older;
`reached_floor` means the caller's own bound was hit. Only the first ever reaches the response.

The structural point is where that gets decided. The loop can run out two ways — a window that
comes back empty or not-found, and a window that comes back holding nothing older than the cursor —
and the first attempt at this fix guarded only one of them, which is exactly how the bug survived
into a second live test. So both routes now fall through to a single terminal block, `on_the_floor`
is computed once per iteration next to the window it describes, and `history_ended = True` has one
assignment site in the function. A third route added later cannot silently miss the check.

`on_the_floor` is "this window's older edge is the floor rather than the calendar" —
`edge - window_seconds(resolution, per_request) <= after`. When it holds, running out means the
caller's bound; when it does not, the window spanned a full page of calendar and running out is the
provider's own bottom. A genuine ending above the floor is therefore still reported, which matters:
it is what lets a job skip chunks below a boundary that really exists.

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
- **One extra gateway request per floored read.** Paging stops on the window *below* the oldest
  candle it found, so a read that ends a few minutes above its floor spends one narrow request to
  learn that. Cheap, and the alternative — guessing that a sliver narrower than one period cannot
  hold a candle — trades a request for an assumption about the provider's bucketing that nothing
  here verifies.
- **A floored read almost never returns `bars` candles**, so the `len(trimmed) < bars` half of the
  `history_ended` condition stops being any protection at all under a floor. It is kept because it
  only ever makes the claim *less* likely, but `not reached_floor` is now the load-bearing half and
  is the one the tests pin.
- **`error.prices.not-found` for a window in a shut market** is still read as an ending when the
  window was not clamped. Left as is: an unclamped window spans a full page of periods, which for
  every resolution this module fetches is wider than any stretch the market is shut for. The bug
  was the *clamped* windows, which are narrow by construction.

## Migration Plan

No schema change, no data migration. Purely a change in what the next fill for a pair with
nothing collected asks for; a pair whose fill already ran under the old behavior is unaffected
until it is untracked and tracked again (or deleted and re-added).
