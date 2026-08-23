# Review — an-observation-is-collected-or-gone

## Verdict

The third state is gone from every layer that could produce it: the route, the tool, the
column, and the `ended` literal on the wire. That completeness is the change — hiding the
state on the screen would have left collected history in the database, unreachable from the
terminal and impossible to remove, which is the same state with a lid on.

Two things a later reader should not mistake for oversights.

**Removal is one SQL statement, and that is the design rather than a shortcut.** `markets`,
`outcomes`, `price_samples`, `collected_ranges` and `sampling_state` all cascade from
`tracked_events`, so `DELETE FROM tracked_events WHERE provider_event_id = $1` is
indivisible by construction. The alternative — calling `delete_history` and then
`end_tracking` — is the same act made of two, and the one that can fail between them,
leaving history without its observation or the reverse.

**`untrack_event` leaving the tool surface is a tightening, not a hole.** The requirement it
sits under says no tool may delete collected history. Once the only way off the list takes
that history with it, a tool for it *would be* a tool that deletes history. What is lost is
named in design.md and is real: a model that hits the observation ceiling can no longer
clear it and must ask the operator. It used to clear it out of somebody else's observation,
which is how the row that started this change appeared.

## Verified

Run at a219c07.

In `modules/polymarket-data`:

```
uv run pytest -q   → 145 passed, 4 skipped   (throwaway PostgreSQL, testcontainers)
uv run ruff check . → All checks passed!
uv run pyright     → 0 errors, 0 warnings, 0 informations
```

In `modules/terminal`:

```
vitest run        → 63 files, 799 passed
tsc -b --noEmit   → clean
eslint .          → clean
contract:check    → Every contract is up to date.
```

In `scripts`: `uv run pytest -q` → 120 passed, 26 skipped, the guide ceiling among them.

`infra/` is untouched. Migration 0003 runs in the module's own lifespan under its lock, so
a merge to `main` leaves production serving with no operator step.

## Findings

**The migration deletes collected history, so it is walked rather than reasoned about.**
`test_0003_takes_the_stopped_observations_and_leaves_the_rest` migrates a throwaway database
to 0002, plants one stopped observation and one live one with a sample each, then migrates
to head and checks that the stopped one and its sample are gone, the live one and its sample
are not, and the column has left the table. This migration runs once against a real database
and there is no second attempt; a test that only asserted the column was dropped would have
passed over the half that destroys data.

**`test_there_is_no_way_to_stop_collecting_without_removing` asserts against the published
document, not against a request.** A `DELETE` to the old path answers 404 either way — the
route being gone and the event not existing are indistinguishable from the outside. What the
test actually needs to know is that the path is not described any more, because a route that
no longer answers but is still in the schema is still a route somebody writes a client for.

**The terminal client dropped `deleteHistory` along with `endTracking`, though the module
kept that route.** Deliberate and worth naming: the screen offers one destructive act, so a
client method for a second one would have no caller — and a method with no caller is a road
somebody takes later, not knowing it was left behind on purpose. The module's contract keeps
`DELETE /events/{id}/history` and its requirement, so the capability is not lost; it is
simply not on a screen. See Gaps.

## Spec coverage

### polymarket-data-api

- *Obserwacje zakłada się i usuwa przez kontrakt* (added) — `routers/observations.py`;
  `tests/test_api.py::TestTracking` covers removal, the 404 and the absent path.
- *Kasowanie danych jest czynnością kontraktu, a nie narzędzia* (modified) — the history
  route is unchanged and its three scenarios still pass; removal is covered by
  `tests/test_store.py::TestRemovingAnObservation`.

### polymarket-data-tracking

- *Usunięcie obserwacji zabiera wszystko i jest jedynym wyjściem z listy* (added) —
  `store.remove_event`; `test_removal_takes_the_markets_outcomes_samples_and_ranges` and
  `test_tracking_it_again_after_removal_starts_from_nothing`.
- *Zakończenie obserwacji zatrzymuje zbieranie i nie rusza danych* (removed) — nothing sets
  `tracking_ended_at` because the column is gone; the migration test is the record of what
  happened to the rows that had it.

### polymarket-data-tools

- *Zestaw zmienia wyłącznie listę obserwacji* (modified) —
  `tests/test_tools_surface.py::test_the_expected_tools_and_no_others` and
  `test_only_the_two_observation_tools_are_declared_as_changing_anything`; the ceiling
  refusal's wording is asserted in `test_store.py::TestTheCeiling` and `test_api.py`.

### terminal-polymarket

- *Zwinięty wiersz identyfikuje obserwację i nie udaje odczytu* (added) —
  `PolymarketView.test.tsx::starts collapsed, carrying what identifies the observation and
  no price`, paired with `shows the prices once the event is unfolded`.
- *Kasowanie zebranej historii jest tutaj i wymaga potwierdzenia* (modified) —
  `RemoveEventDialog.test.tsx`, five tests including the one asserting the dialog no longer
  offers stopping instead.
- *Zakończenie obserwacji nie rusza danych i mówi o tym* (removed) —
  `tracking.test.tsx::offers no way to stop collecting without removing`.

## Gaps

**Deleting an event's history while keeping the observation is now REST-only.** The module's
route and its requirement stand; no screen reaches them. That is a smaller version of the
thing this change was about — a capability with no door — and it was left rather than decided
in passing, because the honest options are opposite: put a second destructive control back on
the screen, or remove the route and its requirement too. Worth a decision, not a default.

**The observation ceiling has not been revisited.** A model can no longer clear it, so the
first refusal an operator actually sees is new information about how often it is reached.
Named as an open question in design.md rather than pre-empted by raising a number nobody has
measured.

**Nothing has been removed against a running stack.** The shapes on both sides of the wire
are covered, and the migration is walked against a real PostgreSQL, but the operator's own
click — remove the Iran row, watch it leave the list — needs the stack up and is theirs.
