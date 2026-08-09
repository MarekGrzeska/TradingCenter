## Verdict

All five pieces shipped: the job runner survives a failure in taking work, a job answers when
something last happened in it, the Data History tab shows that as time-since and marks a running
pull that has gone quiet for five minutes, retry moved off the pair row into a job-wide dialog, and
a configured-but-signed-out terminal sends itself to sign in once per page load. Every confirmation
in the terminal now runs through one `ConfirmDialog`.

One design decision was reversed during implementation and the artifacts were corrected rather than
left describing something that does not exist: `design.md` chose a native `<dialog>` with
`showModal()`, on the assumption that jsdom 26 implemented it. It does not — nor does 25 or 30, all
three ship `HTMLDialogElement-impl.js` as an empty subclass with no `showModal`, `close` or `cancel`
event. Focus handling, the tab trap and `Escape` are therefore written by hand in `ConfirmDialog.tsx`
and tested there. `jsdom` stayed at `^25`; the bump was reverted, not kept.

One spec sentence was also loosened after the code contradicted it — see FIXED-2 below. Nothing else
is knowingly incomplete. Every requirement in this change's specs has a test behind it, including
the structural one (`terminal-dialogs`, "Wszystkie dialogi wychodzą z jednego miejsca") — that one
is held by a test that reads the source rather than renders it, and was checked against a planted
violation of each kind it forbids. What remains open is judgement, not coverage: see Gaps.

## Verified

```
modules/market-data $ uv run ruff check .        → All checks passed!
modules/market-data $ uv run pytest -q           → 517 passed, 7 skipped in 28.19s
modules/terminal    $ pnpm lint                  → clean (eslint .)
modules/terminal    $ pnpm typecheck             → clean (tsc -b --noEmit)
modules/terminal    $ pnpm contract:check        → Contract is up to date.
modules/terminal    $ pnpm test                  → 21 files, 267 passed (242 before this change)
$ openspec validate operator-knows-what-is-happening --strict → valid
```

The terminal suite was run once at the branch point as a baseline (242 passed) before anything was
written, so the 25 new tests are the whole of the difference.

`dialogsComeFromOnePlace.test.ts` was checked against both violations it is meant to catch — a
component rendering `role="dialog"` of its own, and a `window.confirm()` — each planted in
`src/app/`, each failing the suite by name, each then removed. A test asserting the absence of
something is worth exactly what its ability to fail is worth.

## Findings

| Severity | Where | Finding | Status |
|---|---|---|---|
| High | `design.md` — "Wspólny dialog na natywnym `<dialog>`" | The chosen approach rested on jsdom implementing `showModal()`. It does not, in any version — the eight `ConfirmDialog` tests failed at `dialog?.showModal is not a function`. Left as written, the component would have shipped with focus and `Escape` behaviour that no test could reach. | FIXED — approach and rationale rewritten in `design.md`; `jsdom` reverted to `^25`; `ConfirmDialog.tsx` handles focus, the tab trap and `Escape` itself |
| Medium | `specs/terminal-dialogs/spec.md` — "Dopiero powodzenie MUST zamknąć dialog" | Too absolute for behaviour the project already requires: the wizard's acceptance dialog must survive its own success to show which pairs the archive refused (`terminal-data-manager`, "Archiwum odmawia dodania"). Written as it was, the shipped wizard would have violated the new spec. | FIXED — the requirement now allows a success to *replace the question with a result*, and only when the work returns something the view underneath will not show; `closeOnSuccess` carries it in code |
| Low | `market_data/jobs/runner.py:253` | The backoff was logged with `%.0fs`, which prints `0s` for any sub-second value — making the growth untestable without real 5s waits. | FIXED — `%ss`, which reads `5.0s` in production and lets the test assert the sequence |
| Low | `tests/test_jobs_runner.py::test_a_worker_that_dies_says_so` | The old test drove a permanently-broken pool and asserted the worker died. That is now the behaviour the change removes, so the test asserted the bug. | FIXED — split: the survival path is `test_a_worker_survives_a_failure_taking_work_and_carries_on`, and `_report_worker_death` is now tested directly on a task that raised outside the loop's reach |

Nothing further found in the diff. `_fail_orphan` was deliberately left untouched: it settles a chunk
that blew up while held, and a failure to *claim* holds no chunk to settle.

## Spec coverage

| Requirement / Scenario | Proven by |
|---|---|
| **market-data-jobs — Mechanizm wykonujący kawałki przeżywa własną awarię** | |
| Awaria przy przejmowaniu pracy | `tests/test_jobs_runner.py::test_a_worker_survives_a_failure_taking_work_and_carries_on` |
| Awaria trwała | `tests/test_jobs_runner.py::test_a_worker_failing_to_take_work_waits_longer_each_time` |
| Mechanizm jednak się zatrzymuje | `tests/test_jobs_runner.py::test_a_worker_that_dies_says_so` |
| (requirement text: only shutdown ends the loop) | `tests/test_jobs_runner.py::test_a_worker_stopped_while_waiting_out_a_failure_ends_quietly` |
| **market-data-jobs — Zlecenie podaje moment swojej ostatniej aktywności** | |
| Odczyt zlecenia w toku | `tests/test_jobs_store.py::test_a_running_chunk_is_the_jobs_last_activity` |
| Zlecenie stoi | `tests/test_jobs_store.py::test_a_stalled_job_reports_the_same_moment_on_every_read` |
| Zlecenie dopiero utworzone | `tests/test_jobs_store.py::test_a_job_with_nothing_started_yet_dates_from_its_creation` |
| Odczyt zawężony do pary | `tests/test_jobs_store.py::test_a_pair_row_counts_only_its_own_pairs_activity` |
| (wire) | `src/data/archive.test.ts::"lists jobs narrowed to a pair, with the query string carrying the filter"` |
| **terminal-collection-history — Wiersz dociągnięcia otwiera dialog całego zlecenia** | |
| Operator otwiera zlecenie z wiersza | `CollectionHistoryView.test.tsx::"opens the whole job from one pair's row, including pairs the row does not show"` |
| Zlecenie z porażkami | `CollectionHistoryView.test.tsx::"says what the retry covers before doing it, and moves the rows to running once queued"` |
| Wiersz osiągalny klawiaturą | `CollectionHistoryView.test.tsx::"opens from the keyboard too, without a pointer"` |
| Wpis o skasowaniu | `CollectionHistoryView.test.tsx::"opens nothing from a deletion entry, which came from no job"` |
| **terminal-collection-history — Praca w toku pokazuje mierzony postęp** | |
| Zlecenie w toku | `CollectionHistoryView.test.tsx::"shows a measured share of chunks done and candles written so far for a running job"` + `::"says how long nothing has happened, and marks a running pull that has stalled"` |
| Postęp stoi | `CollectionHistoryView.test.tsx::"refreshes on its own every 10 seconds, and stops once the tab is left"` |
| Nic się nie dzieje dłużej niż przez próg bezczynności | `CollectionHistoryView.test.tsx::"says how long nothing has happened, and marks a running pull that has stalled"` |
| (finished pulls say nothing about idleness) | `CollectionHistoryView.test.tsx::"says nothing about idleness for a pull that has finished"` |
| **terminal-collection-history — Nieudane dociąganie ponawia się z zakładki** | |
| Operator ponawia | `CollectionHistoryView.test.tsx::"says what the retry covers before doing it, and moves the rows to running once queued"` |
| Ponowienie stoi przy całości, nie przy parze | `CollectionHistoryView.test.tsx::"keeps retry off the pair's row, where it would promise less than it does"` |
| Ponowienie samo zawodzi | `CollectionHistoryView.test.tsx::"leaves the rows as failed, not running, when the retry request itself fails"` |
| **terminal-identity — Automatyczne logowanie ma jedno podejście** | |
| Logowanie nie doszło do skutku | `autoSignIn.test.tsx::"stops at one attempt when the operator comes back still signed out"` |
| Operator wyszedł z logowania samodzielnie | same test — the two differ only in why the return is still signed out, and the marker is what answers both; `autoSignIn.test.tsx::"marks the attempt before leaving, not after coming back"` proves the marker is written before the page can leave |
| **terminal-identity — Operator loguje się kontem organizacji** | |
| Pierwsze wejście do terminala | `autoSignIn.test.tsx::"sends a signed-out operator through sign-in without being asked"` (the "comes back to the view they were on" half is MSAL's redirect and was already true before this change) |
| Uruchomienie bez skonfigurowanej tożsamości | `autoSignIn.test.tsx::"does not sign in when no identity is configured"` |
| Poświadczenie wygasa w trakcie pracy | unchanged by this change — `entra.ts`'s silent refresh, untouched |
| Sesja wygasła | unchanged by this change; `autoSignIn.test.tsx::"forgets the attempt once the operator is signed in, so a later expiry may try again"` covers the new part (a later expiry may retry) |
| **terminal-dialogs — Pytanie o zgodę jest dialogiem, nie interfejsem w miejscu** | |
| Operator wywołuje działanie wymagające zgody | `ConfirmDialog.test.tsx::"asks in a dialog, and does nothing until the operator confirms"` |
| Komunikat o tym, co się stało | `InstrumentsView.test.tsx` (deletion banner, unchanged) |
| **terminal-dialogs — Dialog nazywa skutek i jego zakres** | |
| Dialog przed działaniem obejmującym wiele rzeczy | `CollectionHistoryView.test.tsx::"says what the retry covers before doing it, and moves the rows to running once queued"` |
| Operator się wycofuje | `ConfirmDialog.test.tsx::"backing out does nothing and leaves the view as it was"` |
| **terminal-dialogs — Dialog zostaje na ekranie, dopóki praca trwa** | |
| Praca trwa | `ConfirmDialog.test.tsx::"stays open while the work runs and will not start it twice"` |
| Praca się udaje | `ConfirmDialog.test.tsx::"closes once the confirmed work succeeds"` |
| Praca udaje się połowicznie | `AddInstrumentWizard.test.tsx::"shows a refusal without hiding the pairs that were accepted"` |
| **terminal-dialogs — Nieudana praca zostaje w dialogu** | |
| Archiwum odmawia | `ConfirmDialog.test.tsx::"keeps a failure inside the dialog, with the question still on screen"` |
| Widok pod dialogiem po nieudanej próbie | `CollectionHistoryView.test.tsx::"leaves the rows as failed, not running, when the retry request itself fails"` |
| **terminal-dialogs — Dialog obsługuje się klawiaturą** | |
| Zamknięcie klawiaturą | `ConfirmDialog.test.tsx::"Escape closes a dialog that is only asking"` + `::"hands focus back to whatever opened it"` |
| Escape w trakcie pracy | `ConfirmDialog.test.tsx::"Escape backs out, but not while the work is in flight"` |
| Fokus po otwarciu | `ConfirmDialog.test.tsx::"keeps the keyboard inside it while it is open"` |
| **terminal-dialogs — Wszystkie dialogi wychodzą z jednego miejsca** | |
| Nowe pytanie o zgodę | `dialogsComeFromOnePlace.test.ts::"has no second component announcing itself as a dialog"` + `::"never falls back to the browser's own confirm()"` |
| Zmiana wspólnego zachowania | same two tests — a behaviour can only be changed in one place while `ConfirmDialog.tsx` is the only component allowed to be a dialog; the behaviours themselves are held by `ConfirmDialog.test.tsx` |

## Gaps

- **The five-minute stall threshold is not calibrated against production.** It is one named constant
  (`STALL_AFTER_SECONDS`), chosen as comfortably above a healthy chunk and far below the forty
  minutes it took to notice. If it turns out to flag jobs merely waiting on the shared limiter, the
  fix is one line.
- **Why the 9 August job stalled is still unknown.** This change makes the next one visible within
  ten seconds; it does not diagnose that one, and was never scoped to (`design.md`, Non-Goals).
