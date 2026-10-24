## Verdict

Shipped: `GET /topic-runs` takes `since` (included) and `until` (excluded), as `GET /videos` does — a zoneless bound is UTC, a range that ends before it starts is refused with the reason — and they combine with the topic filter. The History view has "Od" and "Do" day fields, read in the operator's local time with both days included, and a button that clears them. Without them nothing changes.

Not an oversight: the list is still capped at 100 rows, and inside a range that cap truncates silently — a day with more than a hundred runs shows the newest hundred and does not say so. Rows older than the 30-day retention are gone, so a range before that is empty by construction; the view's "przebiegi z ostatnich 30 dni" note says why.

## Verified

Branch `feat/youtube-topic-runs-by-day`, stacked on `chore/archive-youtube-topic-run-history` (PR #345, open); **uncommitted** when this was written.

- `modules/workbench`: `uv run pytest tests/youtube -q` → 322 passed; `ruff check .` clean, `pyright` 0 errors. The **full** suite was not re-run for this change (the diff is `store.list_runs`, `routers/runs.py` and the rename of the private `views._aware` to `aware`, which nothing else used — checked by grep); CI runs it.
- `modules/terminal`: `vitest run` → 81 files, 974 tests passed; `eslint .` and `tsc -b --noEmit` clean; `node scripts/contract.mjs check` → "Every contract is up to date" (`pnpm` is not on this machine's PATH). Only `contract.youtube.generated.ts` changed: the two query parameters, and `/topic-runs` now documents its 422 as the module's `Problem`.
- `openspec validate youtube-topic-runs-by-day --strict` → valid.
- `db-cost-check`, by hand: `topic_runs` at its 30-day ceiling (57 600 rows) in a throwaway `postgres:17-alpine`. A one-day range and a 30-day range read `topic_runs_ran_at_idx` backward (105 and 103 buffers, 0.13 and 0.12 ms); topic plus range reads `topic_runs_topic_idx` (8 buffers, 0.07 ms). Class C1.
- Not run: `-m live`, a browser.

## Findings

| Severity | Where | Finding | Status |
|---|---|---|---|
| Low | `RunsPanel.tsx` | Inside a range the 100-row cap is not announced (see Verdict). | Accepted — the limit was out of scope |
| Info | `present.dayRange` | A day ends at the next *local* midnight, not 24 hours on, so a day with a clock change is 23 or 25 hours long, as it is on the operator's wall. | Intended; `present.test.ts` › "ends a day at the next local midnight…" |
| — | diff | No defect with a concrete failure path was found. This change was not put through the `code-review` skill; the diff is small and was read against the spec. | — |

## Spec coverage

| Requirement / Scenario | Proven by |
|---|---|
| Historia jest do odczytu przez REST — Zawężenie do tematu | `tests/youtube/test_api.py::test_the_history_of_searches_is_read_newest_first_for_everyone_or_for_one_topic_and_the_list_carries_the_last` |
| … Zawężenie do zakresu czasu (end excluded, newest first) | `test_store.py::test_runs_can_be_narrowed_to_a_range_whose_start_is_included_and_end_is_not_and_to_a_topic_within_it`; `test_api.py::test_a_history_is_read_for_a_range_with_a_zoneless_bound_taken_as_utc_and_a_reversed_range_is_refused` |
| … Zakres i temat razem | same store test (`one_topic`), and the API test (`topic_id` with the range) |
| … Zakres odwrócony | `test_api.py::test_a_history_is_read_for_a_range_with_a_zoneless_bound_taken_as_utc_and_a_reversed_range_is_refused` |
| … Temat bez przebiegu | `test_api.py::test_the_history_of_searches_is_read_newest_first_…` (unchanged) |
| Terminal pokazuje historię — Przebieg, który się nie udał; Pusta historia | `YoutubeView.test.tsx` › "lists the searches newest first…", "narrows the history to one topic, and says when no search has happened yet" (unchanged) |
| … Wybór dni | `YoutubeView.test.tsx` › "narrows the history to days, both included, says when none had a search, and clears them"; `present.test.ts` › "dayRange"; `youtubeApi.test.ts` › "maps a run, narrows by topic, and carries a topic's latest run" (the `since`/`until` on the wire) |
| … Pusty zakres | `YoutubeView.test.tsx` › "narrows the history to days, …" |
| … zakres odwrócony w widoku (not sent) | `YoutubeView.test.tsx` › "says a range that ends before it starts is empty, and does not send it" |

## Gaps

- The date inputs were exercised through `fireEvent.change` in jsdom, not by a person with a browser's date picker; `min`/`max` on the inputs are not tested.
