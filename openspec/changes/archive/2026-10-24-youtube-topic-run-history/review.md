## Verdict

Shipped: every attempt to search a topic is written to `topic_runs` with a report — what the source returned, how much was already known or outside the length bounds, how the rest was screened, and for a failure or a skip the reason. The operator reads it in the Candidates tab (new "Historia wyszukiwań" section, filterable by topic) and sees each topic's latest run in the Topics tab. A repeated failure or skip is written once per UTC day, rows older than 30 days are swept when the next is written, and the agent gets no tool for it.

Knowingly out of scope, and not an oversight: runs of channel discovery (including the new channel filter); the cost of a run in units and tokens (it stays in `usage`, per day); the agent seeing how a topic ended (`TopicBrief` is unchanged — the proposal keeps the history for the operator). History starts at the deploy: earlier searches cannot be reconstructed.

## Verified

Branch `feat/youtube-topic-run-history`, uncommitted when this was written; it also carries the archive of `youtube-channel-filter`.

- `modules/workbench`: `uv run pytest tests/youtube -q` → 320 passed; `uv run pytest -q` (full) → 3010 passed, 11 skipped, run before the last two loop tests were added (those are in the 320). `ruff check .` clean, `pyright` 0 errors. `-m db` tests ran (Docker up).
- `modules/terminal`: `vitest run` → 81 files, 970 tests passed; `eslint src/youtube` clean; `tsc -b --noEmit` clean. `pnpm` is not on this machine's PATH, so the binaries and `node scripts/contract.mjs generate|check` were called directly. Only `contract.youtube.generated.ts` changed (+125 lines); `contract:check` for the terminal: "Every contract is up to date".
- `openspec validate youtube-topic-run-history --strict` → valid.
- `db-cost-check`, by hand (the skill's script has no `youtube` database): a throwaway `postgres:17-alpine` migrated to `0007`, `topic_runs` filled to its ceiling — 20 topics searched every 15 minutes for 30 days, 57 600 rows. All five statements are index-driven and under 1 ms: the "same as previous run" read (`topic_runs_topic_idx`, 6 buffers), the retention sweep (`topic_runs_ran_at_idx`, 2), the all-topics list (backward scan of `ran_at`, 103), one topic's list (4), and the latest run per topic (20 probes of the index, 60 buffers). Class C1.
- Not run: `-m live`.

## Findings

From a `code-review` pass over the diff; all but the last two were fixed in the working tree before this was written.

| Severity | Where | Finding | Status |
|---|---|---|---|
| High | `store.add_run`, `ingest._discover` | A `failed` run was written on every pass for a topic the source keeps refusing — a failed search does not move `last_run_at`, so the topic is retried each pass (~48 rows a day per topic), burying `found` / `nothing_new` in a list capped at 100. | FIXED in the code and tests: a failure or skip that repeats the topic's previous run (same outcome, same error) within the UTC day is not written. **Correction, 24 October:** the spec, design, proposal and README were *not* amended — the edit that was to do it stopped half way and this row said otherwise; the spec and README are put right by `youtube-topic-search-backoff`; `test_store.py::test_a_failure_or_skip_that_repeats_the_previous_run_is_written_once_a_utc_day` |
| Medium | `store.add_run` | The first version of the once-a-day rule asked whether *any* `skipped` row existed since midnight, so a skip in the evening, after the topic had searched fine at noon, was silently dropped and the latest run said `found`. | FIXED by comparing with the previous run, not with the day: `test_store.py::test_a_skip_after_a_run_that_went_through_is_written_though_one_came_earlier_the_same_day` |
| Medium | `ingest._discover` | After `QuotaExceeded` the loop relied on `left = 0` and the next topic's `left < search_cost` to stop; a source whose search cost is 0 would keep searching, and write no `skipped` rows. | FIXED: an explicit `spent` flag |
| Medium | `ingest._propose` | The report's counting indexed a dict by the verdict string; a screener returning another value would raise `KeyError` after the candidates were committed, aborting the pass. | FIXED: an unknown verdict counts as unscreened |
| Low | `ingest.py` | Run messages written to `topic_runs.error` and, from the earlier change, `skip_reason` were Polish strings in backend code; the convention is English in code, and the persisted text cannot be reworded later. | FIXED: English in the backend; the terminal's own sentences stay Polish |
| Low | `store.list_runs` | `$1 IS NULL OR topic_id = $1` can push a generic plan off its index. | FIXED: two statements |
| Low | `store.last_runs` | The column list was built by splitting a string. | FIXED: a tuple of names |
| Low | `CandidatesPanel.tsx` | The candidates read kept polling while the history was shown. | FIXED: `enabled: !history` (the ignored-channels read has no poll) |
| Low | `ingest.py` docstrings | `_screen`'s docstring was stale and two others over the two-line ceiling. | FIXED for the two touched by this change; the rest of the file's longer docstrings pre-date it |
| Info | `tools/films.py`, `tools/watch.py` | The agent's topic views carry no last run, so it still cannot say how a topic ended. | Accepted — a requirement of this change (no tool, no field for the agent); a later change can add it |
| Info | `ingest._note_run` | The history is written on its own connection after the candidates, not in their transaction; a failed write is logged and the pass goes on, so a run can be missing though its candidates are there. | Accepted — the history must not be able to stop the loop |

## Spec coverage

| Requirement / Scenario | Proven by |
|---|---|
| Każda próba … zostawia wpis — Przebieg znajduje nowe filmy | `tests/youtube/test_topic_runs.py::test_a_search_that_found_films_says_what_became_of_each` |
| … Przebieg nie znajduje niczego nowego | `test_topic_runs.py::test_a_search_with_nothing_new_is_written_down_all_the_same` |
| … Źródło zawodzi (przyczyna; termin bez zmian) | `test_topic_runs.py::test_a_search_the_source_refused_says_why_and_is_tried_again_next_pass[SourceUnavailable / QuotaExceeded]` |
| … Usunięty temat | `test_store.py::test_a_topics_last_run_is_its_newest_and_a_run_outlives_its_topic` |
| … `failed`/`skipped` niosą przyczynę (wymóg) | `test_migration.py::test_a_run_that_failed_or_was_skipped_must_say_why` |
| Powtórzona porażka lub pominięcie — Dzień źródła nie starcza przez wiele przebiegów, Nowa doba | `test_topic_runs.py::test_a_day_that_cannot_pay_for_a_search_is_one_skipped_run_per_topic_a_day`; `test_store.py::test_a_failure_or_skip_that_repeats_the_previous_run_is_written_once_a_utc_day` |
| … Źródło zawodzi z tą samą przyczyną / zmienia przyczynę | `test_topic_runs.py::test_a_source_that_keeps_refusing_leaves_one_failed_run_a_day_until_it_says_something_else` (the loop, five passes); `test_store.py::test_a_failure_or_skip_that_repeats_the_previous_run_is_written_once_a_utc_day` (the store) |
| … quota spent mid-pass: the topic fails, the rest are skipped | `test_topic_runs.py::test_a_source_out_of_quota_fails_the_topic_it_stopped_on_and_skips_the_ones_after` |
| … Pominięcie po przebiegu, który się udał | `test_store.py::test_a_skip_after_a_run_that_went_through_is_written_though_one_came_earlier_the_same_day` |
| Wpis mówi, dlaczego kandydaci nie zostali przesiani — Brak modelu | `test_topic_runs.py::test_results_nobody_screened_say_in_the_run_why_not[no_model / day_spent / unusable / no_verdict]`, `::test_a_screened_search_names_no_reason_for_silence` |
| Wpisy starsze niż 30 dni są usuwane — Stary wpis | `test_store.py::test_a_run_older_than_the_retention_goes_with_the_next_one_written` |
| Historia jest do odczytu przez REST — Zawężenie do tematu, Temat bez przebiegu | `test_api.py::test_the_history_of_searches_is_read_newest_first_for_everyone_or_for_one_topic_and_the_list_carries_the_last`; `test_store.py::test_runs_are_listed_newest_first_for_everyone_or_for_one_topic`; limits: `test_api.py::test_a_history_asked_for_too_much_or_nothing_is_refused` |
| … agent without a tool | `test_tools.py::test_the_expected_tools_and_no_others` (the tool set is unchanged) |
| … the new path is on the caller list | `test_caller_access.py` (published paths ⊆ the record) |
| Terminal pokazuje historię — Przebieg, który się nie udał | `terminal/src/youtube/YoutubeView.test.tsx` › "lists the searches newest first, each with its report, and says why one that failed did"; `present.test.ts` › "runSummary" |
| … Pusta historia, filtr po temacie | `YoutubeView.test.tsx` › "narrows the history to one topic, and says when no search has happened yet" |
| … ostatni wynik w Tematach | `YoutubeView.test.tsx` › "shows how each topic's last search ended, in the topics' own tab"; `youtubeApi.test.ts` › "maps a run, narrows by topic, and carries a topic's latest run" |

## Gaps

- **"Agent without a tool"** is proven only by the tool set being unchanged, not by a test about history.
