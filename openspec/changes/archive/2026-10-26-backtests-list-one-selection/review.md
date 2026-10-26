## Verdict

Shipped: one selection box a row in the accent colour, shared by “Porównaj” and “Usuń”; the list is a card per run in a
panel narrower than 64rem and a table above it, with the three R columns only above 80rem and only when some run has R.
A failed run's reason is a line under its row, cut with the whole on hover. Nothing in the package or the contract
changed.

Not an oversight: between 64rem and 80rem the R numbers are not in the table; they are on the run's card below 64rem and
in its report always. The other choice was a table that scrolls sideways, which hid return and Sharpe at 800px — the
numbers the operator reads first.

## Verified

- `modules/terminal`: `vitest run` → 1017 passed; `tsc -b --noEmit` and `eslint .` clean.
- Rendered with Playwright on a throwaway Vite page (not committed) at 380, 800, 1100 and 1300 px panels, dark scheme,
  with runs done, running, failed and one with R: cards at 380/800, the table at 1100 without R and at 1300 with R.
- `openspec validate backtests-list-one-selection --strict` → valid.

## Findings

No findings.

## Spec coverage

| Requirement / Scenario | Proven by |
|---|---|
| Porównanie zaznaczonych… / Dwa warianty obok siebie | `modules/terminal/src/strategies/BacktestsView.test.tsx` — “puts two runs of different strategies side by side, a column each” |
| … / Różne koszty | `BacktestsView.test.tsx` — “says every difference the package named instead of a table” |
| … / Nieudane wśród zaznaczonych | `BacktestsView.test.tsx` — “offers deleting a failed run with a finished one, and says why they cannot be compared” |
| (one box a row, none for a run in progress) | `BacktestsView.test.tsx` — “lets no run in progress be ticked, for comparing or deleting” |

## Gaps

- The layout itself (cards against the table, the R columns' width) has no automated test: rule 3 of the repository's
  test budget forbids asserting Tailwind classes, and the unit environment has no layout. It was checked by eye at four
  widths, as recorded above.
