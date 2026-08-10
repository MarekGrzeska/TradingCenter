## Verdict

Chart pages older candles in when the operator pans left, keeps the frame on the same bars while
doing it, and says which of the three states it is in — loading, start of history, failed page. The
slot's symbol picker is a plain select over what the archive collects. Two things are deliberate and
should not read as oversights: "start of history" is remembered until symbol, resolution or source
changes (a pair backfilled by a collection job in the meantime will not re-page until then), and the
series has no upper bound — a long enough drag keeps every candle it fetched in memory.

## Verified

In `modules/terminal`, on 2d7be19:

- `pnpm typecheck` — clean.
- `pnpm lint` — clean.
- `pnpm test` — 21 files, 272 tests, all passing.
- `node scripts/contract.mjs check` — "Contract is up to date."
- `openspec validate chart-loads-older-candles --strict` — valid.

Not run: the stack against a live archive. The paging path is proven against `ControllableSource`,
including the case the fake now reproduces on purpose — a time scale that notifies its subscribers
about a range it was *told* to take, which is what makes a self-triggering loop possible at all.

## Findings

| Severity | Where | Finding | Status |
|---|---|---|---|
| Medium | `src/chart/Chart.tsx:184` (as first written) | A page landing corrects the frame, the time scale reports that correction as a range change, and the handler treated it like a pan — asking for the next page, and that one for the one after it. A single drag would have walked the whole archive. | FIXED in 28148c2 (`requestedFromRef`, and `testDoubles.ts` made to notify on `setVisibleLogicalRange` so the loop is reproducible) |
| Low | `src/chart/Chart.tsx:291` | The gap-fill path (a bar older than everything drawn, redrawn wholesale) skipped the frame correction, so such a bar nudged the chart one candle sideways. | FIXED in 2d7be19 |
| Low | `src/chart/useOlderBars.ts:118` | A failed page blocks further paging until `retry`, by design — but the block is per pair and survives an archive that has since come back, until the operator clicks. Judged correct: the alternative is a request loop against something that is down. | Open by decision |

## Spec coverage

| Requirement / Scenario | Proven by |
|---|---|
| **Wykres dociąga starszą historię przy przewijaniu w lewo** | |
| Przewinięcie poza najstarszą świecę | `src/chart/Chart.test.tsx::asks for a range ending at the oldest drawn candle` |
| Kadr nie ucieka spod kursora | `src/chart/Chart.test.tsx::keeps the operator looking at the same candles after a page lands` |
| Przewijanie w trakcie odczytu | `src/chart/Chart.test.tsx::says it is loading, and does not start a second read while one is in flight`; `src/chart/Chart.test.tsx::does not chain a second page off its own frame correction` |
| Zmiana symbolu albo rozdzielczości w trakcie dociągania | `src/chart/Chart.test.tsx::drops a page that arrives after the symbol changed` |
| **Wykres mówi, co się dzieje ze starszą historią** | |
| Trwa dociąganie | `src/chart/Chart.test.tsx::says it is loading, and does not start a second read while one is in flight` |
| Archiwum nie ma nic starszego | `src/chart/Chart.test.tsx::walks past empty windows before calling it the start of history` |
| Odczyt starszej historii się nie powiódł | `src/chart/Chart.test.tsx::keeps the drawn candles when a page fails, and retries on demand` |
| **Slot przyjmuje wyłącznie instrument archiwizowany** | |
| Wybór instrumentu do slotu | `src/grid/GridView.test.tsx::changes one slot's instrument without disturbing the others`; `src/grid/GridView.test.tsx::keeps a hidden slot's instrument when shrinking and re-expanding` |
| Instrument spoza archiwizowanych | `src/grid/GridView.test.tsx::offers every archived symbol and nothing else` |
| Nic nie jest archiwizowane | `src/grid/GridView.test.tsx::says nothing is archived, and points to Instruments, instead of an empty list` |
| Listy archiwizowanych nie da się odczytać | `src/grid/GridView.test.tsx::keeps a slot's instrument when the archived list can't be read, and lets the picker say so` |

Beyond the specs, one decision from design.md carries its own test:
`src/chart/Chart.test.tsx::does not throw the frame back to the right when the stream reconnects`
(`fitContent()` only on the first draw of a pair).

## Gaps

- "Zmiana symbolu albo rozdzielczości w trakcie dociągania" is proven for a changed symbol only.
  Resolution and source run through the same generation guard in `useOlderBars` — one effect, one
  dependency list — so the second test would exercise the same line with a different argument.
- No test drives the real `lightweight-charts` time scale; every chart test in this module runs
  against the stub, for the reason recorded in `testDoubles.ts` (a canvas jsdom cannot assert on).
  What the paging depends on from the real library — that `setVisibleLogicalRange` notifies
  subscribers — is asserted only of the fake.
