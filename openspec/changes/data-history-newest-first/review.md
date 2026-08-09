## Verdict

Shipped. `Data History` sorts on time alone, newest first, with symbol and the canonical
resolution order kept on only as a tiebreak. One sort comparator, one spec requirement, four
tests.

The two ordering tests that already existed pass **unchanged**, which is what tasks.md 2.4
asked them to prove: both concern a single pair, so a global time order cannot disturb them.
Had either needed editing it would have meant the change reached further than intended.

## Verified

- `pnpm lint`, `pnpm typecheck` → clean
- `pnpm test` → `224 passed` (was 221; +3 from this change)
- `openspec validate data-history-newest-first --strict` → valid

## Findings

| Severity | Where | Finding | Status |
|---|---|---|---|
| Medium | `combinedEntries` | Sorting on `b.at - a.at` alone is not deterministic here. A wizard submission creates every pair in one go, so seven rows share one `createdAt` to the second — and the two lists being merged come from two independent polls, so the input order is not fixed either. `Array.prototype.sort` being stable is no help when what it is sorting arrives differently each time: the tab would reshuffle under a reader while polling. | Fixed before it shipped — ties fall back to symbol then resolution, both derived from the data and identical on every read. `test_orders_events_of_the_same_moment_the_same_way_however_they_arrive` renders twice with the input reversed |

## Deviations from design.md

None. The comparator, the tiebreak and the reasoning are as designed.

## What this cost, stated plainly

A deletion no longer sits next to the pull it undid. Symbol was the first sort key, so those
two events were adjacent whatever else had happened; now other pairs' events fall between
them, and reading "why does this pair's range look shallower now" as one story is harder.

Taken deliberately, and the proposal names it rather than trading it away quietly. The
adjacency was never a guarantee worth much — it held because two events shared a symbol,
which says nothing about when — and the reading it supported is the tab's second question.
The first is "what just happened", which the alphabet answered badly and for which there was
no workaround at all.

If it bites, the answer is filtering by pair, not a different sort. That is a separate change
and should argue for itself.

## Gaps

- **Not seen on a running stack.** The tests assert row order by `data-testid`, which is the
  DOM order and therefore the visual one, so there is little room for it to look different —
  but nobody has watched the tab reorder itself while polling with a real job in flight.
- **`at` for a job is `createdAt`, not when it finished**, so a long job stays where it
  started rather than rising as it progresses. That is the existing behaviour and matches the
  column header (`when`); changing it would have been a second decision inside this one, and
  is named here in case the tab ever reads oddly during a slow pull.
