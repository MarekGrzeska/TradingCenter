## Verdict

Shipped: a topic search the source answered with a refusal or with something unusable — and so charged for — or that ran into
the source's spent quota now holds the topic back for its own interval (`topics.retry_at`), so a failing topic costs no more
than a working one. A search the source never answered (a network error, not charged) is tried again on the next pass, as
before. The hold does not move `last_run_at`, so the next search that goes through still looks from the last one that did,
and that search lifts the hold. `GET /topics` and the Topics tab say until when a topic is held. The error a failed run records
now carries Google's own reason and sentence, so the history will say *why* searches fail.

Also put right: the spec and README of `youtube-topic-run-history` now say what the code has done since that change's review
(a failure or skip repeating the topic's previous run within the UTC day is written once); the archived review's claim that
they had been amended is corrected in place.

Not done, and not an oversight: why production's searches fail is still unknown — the topics are paused, and the cause will
show in the history on the first search after this is deployed and they are resumed. Pausing and resuming a topic does not
lift a hold. The Gemini 403 is a separate problem.

## Verified

Branch `feat/youtube-topic-search-backoff`, committed with this review. It also carries the archive of
`youtube-topic-runs-by-day` (its two modified requirements synced into `youtube-data-topic-runs`).

- `modules/workbench`: `uv run pytest tests/youtube -q` → 326 passed; full `uv run pytest -q` → 3018 passed, 11 skipped.
  `ruff check .` clean, `pyright` 0 errors. `-m db` ran (Docker up).
- `modules/terminal`: `vitest run` → 81 files, 975 passed; `eslint .`, `tsc -b --noEmit` clean; `node scripts/contract.mjs check`
  → "Every contract is up to date" (only `contract.youtube.generated.ts`, +5 lines: `retry_at`).
- `openspec validate youtube-topic-search-backoff --strict` → valid; `openspec validate --specs --strict` → 94 passed;
  `trim-openspec-archive.sh --check` → trimmed.
- Production, read-only, over SSH (the facts the proposal stands on): `usage` — `data_api` 5712 / 8000 / 7974 on 22–24 Oct;
  1 active channel, 8 active topics at 360 min, none with a `last_run_at`, 0 candidates ever; `topic_runs` — 8 × `skipped` at
  13:46 UTC on 24 Oct. `DataApiSource._get` counts units before judging the answer (`data_api.py`), so each refused search
  was charged.
- No new statement on a timer: the hold is one `UPDATE` by primary key per failed search, and the due-check reads columns the
  loop already reads.

## Findings

| Severity | Where | Finding | Status |
|---|---|---|---|
| High | `youtube-topic-run-history` spec, README, archived review | The spec said a `failed` run is written "at every failure" and the README "once per topic per UTC day" for skips only, while the code wrote a repeated failure or skip once per day; the archived review claimed the spec had been amended. | FIXED here (delta MODIFIED requirement, README, a correction in the archived review) |
| Medium | `ingest._discover` | A search that failed after being charged was retried on every pass — 8 topics × 101 units every 30 minutes spent the 8 000-unit day by morning and stopped the channels' discovery with it. | FIXED: the hold. `test_topic_runs.py::test_a_search_the_source_refused_says_why_and_waits_the_topics_interval_before_it_is_paid_for_again[SourceRefused / QuotaExceeded]` |
| Low | `data_api._error_reasons` | `response.json().get(...)` would raise `AttributeError` on an error body that is JSON but not an object. | FIXED in passing (`_error`) |
| Info | `ingest._discover` | Two tests of mine were wrong before the code was: a hold of exactly the interval is due at the interval (`>=`), and the reason and Google's sentence are joined by a comma. | Tests corrected |

## Spec coverage

| Requirement / Scenario | Proven by |
|---|---|
| Każda próba … — Źródło zawodzi (failed, cause, held for the interval) | `tests/youtube/test_topic_runs.py::test_a_search_the_source_refused_says_why_and_waits_the_topics_interval_before_it_is_paid_for_again[…]` |
| … Źródło nie odpowiada (retried on the next pass, not held) | `test_topic_runs.py::test_a_search_the_source_never_answered_is_tried_again_on_the_next_pass` |
| … Udane wyszukiwanie po porażce (hold lifted, window from the last success) | `test_topic_runs.py::test_a_search_that_goes_through_after_a_hold_lifts_it_and_looks_from_the_last_one_that_went_through` |
| … paid vs unpaid at the source | `test_data_api.py::test_an_answered_error_is_a_paid_refusal_that_says_what_google_said_and_no_answer_costs_nothing`, `::test_a_spent_quota_is_told_apart_from_a_refusal_and_still_counted` |
| … the other scenarios (found, nothing new, removed topic) | unchanged tests from `youtube-topic-run-history` |
| Pominięcie … raz na temat na dobę — all five scenarios | `test_store.py::test_a_failure_or_skip_that_repeats_the_previous_run_is_written_once_a_utc_day`, `::test_a_skip_after_a_run_that_went_through_is_written_though_one_came_earlier_the_same_day`; `test_topic_runs.py::test_a_day_that_cannot_pay_for_a_search_is_one_skipped_run_per_topic_a_day`, `::test_a_source_that_keeps_refusing_leaves_one_failed_run_a_day_until_it_says_something_else` |
| Temat odroczony po porażce mówi, do kiedy — Temat odroczony | `test_api.py::test_a_topic_held_back_after_a_refused_search_says_until_when`; `YoutubeView.test.tsx` › "says when a topic held back after a refused search is next tried, and nothing once that moment has passed" |
| … Temat bez odroczenia | same API test (`retry_at` null on a new topic); `test_topic_runs.py::test_a_search_that_goes_through_after_a_hold_lifts_it…` |

## Gaps

- The production cause of the failing searches is not reproduced or tested; it is the next thing the history will show.
