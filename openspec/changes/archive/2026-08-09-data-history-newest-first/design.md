## Context

`combinedEntries` in `history/CollectionHistoryView.tsx` merges jobs and deletions into one list and
sorts it by symbol, then by interval in the canonical resolution order, then newest first within the
pair. Every entry already carries an `at` — `job.createdAt` or `deletion.deletedAt` — so the data
needed for a time ordering is there and unused as a primary key.

## Goals / Non-Goals

**Goals:**

- The whole table reads newest first, whatever the instrument.
- Ties are stable across refreshes: the tab polls, and a list that reshuffles under a reader is
  worse than one ordered badly.

**Non-Goals:**

- Grouping, collapsing or sectioning by instrument. That is a different feature with a different
  cost, and this change is not a stepping stone toward it — if grouping is wanted later it will
  argue for itself.
- Making the order selectable. One order that answers the tab's main question beats two that need
  a decision before reading.
- Touching what a row shows. Rows stay per instrument and per interval.

## Decisions

### Sort on `at` alone, with a stable tiebreak

```ts
return entries.sort((a, b) => b.at - a.at || tiebreak(a, b));
```

`at` is seconds, and two events can share one — most plainly the seven pairs of a single wizard
submission, which are created together and carry the same `createdAt`. Left to `b.at - a.at` alone
that is a tie, and while `Array.prototype.sort` is specified as stable, the *input* order is not:
jobs and deletions arrive from two independent reads and the tab polls both. Stability of the sort
does not help when what is being sorted arrives in a different order.

So ties fall back to symbol and then to the canonical resolution order — the very keys being removed
as primary ones. They are wrong as the main ordering and exactly right as a tiebreak: derived from
the data, total, and identical on every poll.

### The deletion no longer sits next to the pull it undid

Today symbol is the first key, so a pair's pull and the deletion that later removed it are adjacent
whatever else happened. After this change other pairs' events fall between them, and reading "why
does this pair's range look shallower now" as one story gets harder. That is a real loss and the
proposal names it rather than trading it away quietly.

Taken anyway, for two reasons. The adjacency was never guaranteed — a pair pulled, deleted, and
pulled again already interleaves its own three events with nothing between them only because they
share a symbol, which says nothing about *when*. And the reading it supports is the second question
this tab is asked; the first is "what just happened", which the alphabet answers badly and for which
there is no workaround, while the pair story can still be followed by reading the symbol column.

## Risks / Trade-offs

- **A busy archive interleaves pairs**, so a reader following one instrument scans more. Accepted
  above; if it bites, the answer is filtering, not a different sort.
- **`at` for a job is `createdAt`, not when it finished.** A long job stays where it started rather
  than rising as it progresses. That matches the existing behaviour and the column header (`when`),
  and changing it would be a second decision smuggled into this one.

## Migration Plan

None. A view-layer ordering change with no stored state and no contract involvement.
