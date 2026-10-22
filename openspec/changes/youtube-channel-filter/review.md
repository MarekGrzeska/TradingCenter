## Verdict

Shipped: a channel may carry a free-text filter; the films of its latest listing that the archive has not stored are judged by
the screening model on metadata alone, in one call per channel and pass. A passed film travels the old road, a rejected one is
kept as `filtered_out` with the model's sentence (judged once, never transcribed), and a film nobody could judge is not stored
and comes back with the next listing. REST, the agent's `follow_channel`, the terminal and the simulation all carry it.

Knowingly incomplete, and not an oversight: (1) a channel that publishes more than the fifteen films its listing holds between
two judgements loses the oldest — the price of "waits" without a new state (design.md, decision 1); (2) a changed filter does not
re-judge what was already turned away; (3) the cap on paid answers without a verdict is counted in the process's memory, so a restart starts each count again —
a few more answers, never an unbounded number; (4) the channel frame was exercised only against the simulation and a fake client, never
a real model — its wording, including the tie-break below, is untested against one.

Not in the spec and worth knowing a year on: the channel frame tells the model to answer `proposed` when title and description do
not let it tell ("a film wrongly passed costs a transcript, one wrongly dropped is never seen"). That is a judgement call made
while implementing, recorded here and in `screening.py`, not a requirement.

## Verified

Run from the working tree of branch `feat/youtube-channel-filter`, **uncommitted** (nothing in this change has a commit yet):

- `modules/workbench`: `uv run pytest -q` → 2985 passed, 11 skipped (before the review fixes and the tests they brought);
  after them `uv run pytest tests/youtube -q` → 300 passed. `uv run ruff check .` clean, `uv run pyright` 0 errors. `-m db`
  tests ran (Docker was up).
- `modules/terminal`: `vitest run` → 81 files, 964 tests passed; `eslint .` clean; `tsc -b --noEmit` clean.
  `pnpm` is not on this machine's PATH, so the binaries and `node scripts/contract.mjs generate|check` were called directly:
  "Every contract is up to date" (terminal), "The contract is up to date" (pocket). Only `contract.youtube.generated.ts` changed.
- `modules/trading-mcp`: `uv run python scripts/contract.py check` → "Contract is up to date".
- `openspec validate youtube-channel-filter --strict` → valid.
- `db-cost-check`, by hand, because the skill's script has no `youtube` database in the dev container: a throwaway
  `postgres:17-alpine` migrated to `0006`, 200 000 synthetic films, two statements EXPLAINed. `in_archive` (the one query the
  loop gained, per filtered channel and pass): `Index Only Scan using videos_pkey`, 17 buffers for 15 ids — C1. The changed
  `list_films` predicate: still `videos_published_idx`, the state test is a `Filter` on rows already read — C2, as before.
- Not run: `-m live`, and any real OpenAI call.

## Findings

| Severity | Where | Finding | Status |
|---|---|---|---|
| Low | `migrations/youtube/versions/0006_channel_filter.py` | Dropping and re-adding `videos_state_is_known` takes an ACCESS EXCLUSIVE lock and rescans `videos`. Harmless while the YouTube archive is off in production (README: unset is today's production); on a large table the constraint should be added `NOT VALID` and validated apart. | Open — noted for the production-enabling change |
| Low | `youtube_data/views.py`, `contract.py` | The spec says the state "gives the cause" a filtered channel's films wait; `/state` gives three facts (`model_configured`, the analyser's `exhausted`, `channels_filtered`) and the sentence is composed in the terminal (`present.warnings`). Another client of `/state` must compose it itself. | Accepted |
| Low | `terminal/src/youtube/FilmCard.tsx` | After "Analizuj mimo to" the list reloads and the card leaves the `filtered_out` view, taking its "Przyjęte" note with it; the film is then in the ordinary list. Correct, but the confirmation is brief. | Accepted |
| Info | `youtube_data/sim/scenarios/default.json` | `simfilm0008` is now `screening: rejected`, which also makes the `zło` topic search reject it in the simulation. No test depended on it; the README says so. | Accepted |
| High | `youtube_data/ingest.py` `_through_filter` | A film the model kept answering nothing usable about (a refusal, a broken schema, or a film left out of the answer — one hostile title can do it to a whole batch) was asked about, and paid for, on every pass for as long as the listing held it, draining the day's tokens for every other reader. | FIXED (working tree, uncommitted): after `JUDGE_MAX_FAILURES` (3) paid answers without a verdict the film is kept `filtered_out` saying it could not be judged; an absent, spent or unreachable model counts none. Spec amended. `test_channel_filter.py::test_a_film_the_model_keeps_answering_nothing_about_is_kept_filtered_out_saying_so`, `::test_a_model_nobody_could_reach_spends_none_of_a_films_answers` |
| Medium | `ingest.py` `_through_filter`, `store.release_filtered`, `terminal/…/present.ts` | A live stream or premiere was judged while running and, if rejected, kept `filtered_out` with `live_status` frozen at `live`: the card said "trwa transmisja" for ever, and "analyse anyway" released a film `due_for_transcription` never picks up. A film of unknown length went to the model too. | FIXED (working tree): such films wait unjudged until the source lists them ended and with a length. `test_channel_filter.py::test_a_stream_still_running_waits_unjudged_and_is_judged_once_it_has_ended` |
| Low | `terminal/src/youtube/dialogs.tsx` | Following a channel already on the list dropped the filter typed in the dialog without a word. | FIXED (working tree): the "already followed" dialog says the filter was not set and where it is changed. `YoutubeView.test.tsx` › "says a filter typed for a channel already followed was not set, and where it is changed" |
| Low | `youtube_data/tools/watch.py` `analyse_video` | The description promised "a film already here keeps its own" prompt, which a filtered-out film does not; and did not say the call overrides the operator's filter. | FIXED (working tree): the description says both. |
| Low | `youtube_data/watchlist.py` `analyse_film` | The result of `release_filtered` was ignored: a second caller racing the first was told `process=True` for a film already on its road. | FIXED (working tree): a release that matched nothing re-reads the film and answers as for any film already here. |
| Info | `contract.py`, migration, `dialogs.tsx` | The 1–1000 limit is stated in the check, the migration's CHECK, the textarea's `maxLength` and two descriptions, not as `Field(max_length=…)`; the generated contract does not carry it. Moving it to `Field` would change a refusal's shape from the module's `Problem` to FastAPI's validation list. | Accepted |
| Info | `store.py` `in_archive` / `already_known` | Two near-copies of "is this film known", differing in whether a candidate counts. | Accepted — merging them costs a second query or a flag on a hot path |

Gaps found while mapping the spec in pass 2 and closed in the same session (tests added, no code change): the token cost of a
judgement, taking a filter off against films found later, a rejected film put through the loop after being named, and a named
prompt on release. Each was untested when the first green run was reported.

## Spec coverage

| Requirement / Scenario | Proven by |
|---|---|
| Kanał ma opcjonalny filtr, a bez niego przetwarza wszystko — refusal of blank / over-long filter | `tests/youtube/test_api.py::test_a_filter_that_says_nothing_or_too_much_is_refused_and_changes_nothing`; `test_tools.py::test_the_agent_may_give_a_new_channel_a_filter_and_cannot_change_that_of_one_already_followed` (over-long) |
| … Kanał bez filtra | `test_channel_filter.py::test_a_channel_without_a_filter_is_never_put_to_the_model` |
| … Agent obserwuje kanał z filtrem | `test_tools.py::test_the_agent_may_give_a_new_channel_a_filter_and_cannot_change_that_of_one_already_followed` |
| … Agent obserwuje kanał już na liście | same test; `test_api.py::test_a_channels_filter_is_set_kept_when_something_else_changes_and_taken_off_only_by_a_null` for the operator's REST |
| … Usunięcie filtra | `test_channel_filter.py::test_taking_the_filter_off_leaves_what_it_turned_away_and_passes_what_comes_after`; `test_store.py::test_a_channel_filter_is_set_kept_and_taken_off_only_when_asked` |
| Nowy film kanału z filtrem jest oceniany po metadanych przed transkrypcją — spends tokens, no transcript | `test_channel_filter.py::test_judging_a_film_spends_tokens_and_no_transcript` |
| … only unseen, worth-a-transcript films are put to the model | `test_channel_filter.py::test_only_films_the_archive_has_not_seen_and_are_worth_a_transcript_are_put_to_the_model` |
| … Film spełnia warunek | `test_channel_filter.py::test_a_film_that_passes_goes_on_and_one_that_does_not_is_kept_unread_with_the_reason` |
| … Film nie spełnia warunku | same test (state `filtered_out`, reason set, no transcript row, only the passed film's seconds spent) |
| … Ten sam film w kolejnym przebiegu | `test_channel_filter.py::test_a_film_is_put_to_the_model_once_however_often_its_channel_lists_it` |
| … Trwająca transmisja | `test_channel_filter.py::test_a_stream_still_running_waits_unjudged_and_is_judged_once_it_has_ended` |
| … Tytuł próbuje sterować oceną | `test_screening.py::test_a_channels_criteria_stand_apart_from_the_data_a_stranger_wrote`, `::test_a_channel_is_screened_by_its_own_frame_and_the_same_schema` — the message structure and frame, **not** a model's obedience (see Gaps) |
| … never handed to alerts | by construction: a `filtered_out` film never reaches `analysed`; no test of its own (see Gaps) |
| Film, którego nie dało się ocenić, czeka — Wyczerpany limit tokenów, Brak modelu, unusable answer | `test_channel_filter.py::test_a_film_nobody_could_judge_is_neither_stored_nor_transcribed_and_is_judged_when_somebody_can[no model / no tokens left / unusable answer]` |
| … no verdict for one film | `test_channel_filter.py::test_a_film_the_model_gave_no_verdict_for_waits_while_the_others_are_stored` |
| … Model raz po raz nie wydaje werdyktu | `test_channel_filter.py::test_a_film_the_model_keeps_answering_nothing_about_is_kept_filtered_out_saying_so` |
| … Nieosiągalny dostawca | `test_channel_filter.py::test_a_model_nobody_could_reach_spends_none_of_a_films_answers` |
| … the state names the cause | `test_api.py::test_a_film_the_filter_turned_away_is_left_out_of_the_list_until_asked_for_and_can_be_analysed_anyway` (`channels_filtered`); `terminal/src/youtube/present.test.ts` › "says the films of a filtered channel wait while no model can judge them, and only then" |
| Zmiana filtra dotyczy filmów wykrytych po niej — Złagodzenie filtra | `test_channel_filter.py::test_taking_the_filter_off_leaves_what_it_turned_away_and_passes_what_comes_after` |
| Odrzucony film można przetworzyć ręcznie — Analizuj mimo to | `test_channel_filter.py::test_a_film_the_filter_turned_away_is_transcribed_and_read_once_somebody_names_it`; `test_api.py::test_a_film_the_filter_turned_away_is_left_out_of_the_list_until_asked_for_and_can_be_analysed_anyway` |
| … named prompt, else the channel's | `test_store.py::test_a_film_released_by_a_named_prompt_is_read_by_it_and_otherwise_by_its_channels` |
| Odrzucone filmy są domyślnie ukryte — Lista bez wskazanego stanu / Lista odrzuconych | `test_api.py::test_a_film_the_filter_turned_away_is_left_out_of_the_list_until_asked_for_and_can_be_analysed_anyway`; `test_store.py::test_a_filtered_out_film_is_kept_with_its_reason_and_listed_only_when_asked_for` |
| … terminal shows, sets and clears the filter | `terminal/src/youtube/YoutubeView.test.tsx` › "follows a channel with the filter typed in the dialog…", "sets a channel's filter from its row, takes it off when emptied, and keeps the module's refusal in the dialog" |
| … terminal shows a turned-away film with reason and the action | `YoutubeView.test.tsx` › "lists what a filter turned away only when asked, with the reason, and analyses it anyway"; `present.test.ts` › "says where an unread film is…" |
| Storage: `filtered_out` survives, needs a reason, is not dropped | `test_store.py::test_a_filtered_out_film_seen_again_is_not_stored_again_and_survives_the_drop`; `test_migration.py::test_a_channel_from_before_the_filter_has_none_and_a_filtered_out_film_must_say_why` |

## Gaps

- **A model's obedience to the criteria and its resistance to a hostile description** is not tested: the screening tests prove
  what the model is *sent* (criteria apart from data, the channel frame, the strict schema), and the loop tests use the
  simulated verdict. No test calls a real model.
- **"Never handed to alerts"** has no test of its own; it follows from `filtered_out` never becoming `analysed`.
- **`/state` as a sentence** — see the second finding; the cause is three fields plus the terminal's composition.
