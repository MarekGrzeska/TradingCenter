# Review — a-strategy-can-be-clicked-together

## Verdict

The change ships whole and reverses what it set out to reverse: a catalogue entry now comes
from the deployed image **or** from an immutable revision the operator wrote, and nothing
below `resolver.py` can tell which. The loop, the gates, the record and the two surfaces were
not given a branch of the shape "if this one was configured" — that absence is the claim, and
`tests/test_layering.py` plus the resolver's single call site are what hold it.

Two things a later reader should not mistake for oversights.

**The `Settled` node was not in the plan and is load-bearing.** Design decision 2 listed the
vocabulary without it, and the twin of `baseline_ma_cross` could not be written faithfully
without it: the coded entry checks settlement *before* it checks the range, so on a bar where
the averages have not filled **and** the range is zero it answers "not settled", while a
twin relying on three-valued propagation answers "the range is zero". One state, two
refusals, and the wrong one is a lie about why nothing happened. `Settled` is the one node
that answers rather than propagating, which lets a rule state settlement as its own first
guard. That case is in `tests/test_baseline_rule.py` under its own name.

**The twin carries one feature more than the coded entry, on purpose.** `baseline.py`
computes `extension_atr` only on the bar it enters; the interpreter computes features in one
place for every rule, so a refusal from the twin carries both. The golden test asserts
equality of action, reason, levels, reward-over-risk and score, and a *superset with equal
values* for the features — written that way for this and nothing else. Making the two
identical would have meant per-branch features, which is complexity bought for a cosmetic
difference in the direction of more information.

## Verified

Run at 4087561.

In `modules/strategy`:

```
uv run pytest -q      → 300 passed, 1 warning
uv run pytest -q -m db → 84 passed, 216 deselected   (throwaway PostgreSQL, testcontainers)
uv run ruff check .   → All checks passed!
uv run pyright        → 0 errors, 0 warnings, 0 informations
```

In `modules/terminal`:

```
vitest run          → 63 files, 797 passed
tsc -b --noEmit     → clean
eslint .            → clean
contract:generate   → contract.strategy.generated.ts rewritten
contract:check      → Every contract is up to date.
```

In `scripts`: `uv run pytest -q` → 120 passed, 26 skipped, the guide ceiling among them.

`infra/` is untouched: this change adds no resource, no identity and no entry to any
`allowed_applications`. Migration 0003 is additive throughout and runs in the module's own
lifespan under lock 8080, so a merge to `main` leaves production serving with no operator
step.

## Findings

**The terminal's CI pairing had a hole this change would have fallen into.**
`checks.yml` filtered the terminal on `strategy/strategy/(contract|openapi).py`. The rule
vocabulary is defined once, in `rule.py`, and `contract.py` publishes those very models
rather than restating them — so a node added there moves the generated types with neither
other file edited, and `contract:check` would not have run. Widened to
`(contract|openapi|rule).py`, with the reason written beside the three pairings that were
already there. Found by task 8.2, which existed to ask exactly this.

**A stored revision an older image cannot read is a refusal, not a crash.** Not in the plan
and it should have been: a rollback below the image that wrote a rule is ordinary. `resolver.
parse` turns a validation failure into this module's own error, the loop skips that one watch
the way it already skips a strategy the image no longer carries, and `all_available` leaves
it out of the list rather than failing the whole listing. Both paths have tests.

**`test_the_rest_caller_reaches_rest` moved from `/strategies` to `/`.** `/strategies` now
merges both sources and therefore needs a database, which that fixture has none of. What the
test is about is the gate, and `/` is the only route in this application that can answer
without one. The refusal cases still use `/strategies`, because they never reach a route body.

## Spec coverage

### strategy-configurator

- *Reguła jest danymi w zamkniętym słowniku węzłów* — `rule.py`; `tests/test_rule.py` covers
  a node kind outside the vocabulary, the ceilings on nodes and depth, and the arities that
  cannot mean anything.
- *Brak odczytu nie jest sygnałem, a odmowa jest domknięta* — `interpreter.py`;
  `tests/test_interpreter.py::TestThreeValuedLogic` covers Kleene's two shortcuts and the
  undetermined-refuses direction, `TestTotality` covers division by zero and a stop that
  works out to its entry.
- *Definicja jest odrzucana w chwili zapisu* — `rule_validation.py`;
  `tests/test_rule_validation.py` covers every refusal in the requirement, including the
  tunable ranging further than the indicator it drives, and `tests/test_definitions.py`
  covers the archive being unreachable leaving nothing saved.
- *Rewizja jest niezmienna, a obserwacja ją przypina* — migration 0003, `store.py`,
  `routers/strategies.py`; `tests/test_revisions.py::TestPinning`.
- *Strategia odniesienia pozostaje kodem i jest miarą interpretera* —
  `catalogue/baseline_rule.py`; `tests/test_baseline_rule.py` over ten states, plus
  `test_naming_only_coded_entries_reaches_no_database`.

### strategy-catalogue (modified)

- *Wpis z rewizji obok wpisu z obrazu* — `resolver.py`;
  `tests/test_revisions.py::TestResolving::test_both_sources_are_one_catalogue`.
- *Odczyt, który się nie ustabilizował* — the declared `unsettled_reason`, asserted in
  `tests/test_interpreter.py`.
- *Decyzja wraca do swojej rewizji reguły* — `decisions.strategy_revision_id` with the
  version joined in; `tests/test_revisions.py::TestWhatOneDecisionRemembers`.

### strategy-runtime (modified)

- *Odtworzenie oceny po zmianie definicji* —
  `test_a_recorded_decision_is_re_decided_from_what_was_written_down`, which moves the
  definition on first and still lands on the recorded decision. This is the acceptance test
  of the change.

### strategy-backtest (modified)

- *Przebieg nad rewizją z bazy* and *Zestawienie dwóch rewizji jednej definicji* —
  `backtest/report.py`, `backtest/__main__.py`; `tests/test_backtest.py`.

### terminal-strategy-configurator

- *Wybieraki konfiguratora pochodzą z katalogu archiwum* —
  `DefinitionDialog.test.tsx`'s first test asserts a picker built from a catalogue naming an
  indicator this repository has never heard of.
- *Ekran pokazuje rewizję jako pochodzenie* — `DecisionRow.tsx`, `DefinitionsPanel.tsx`;
  `DefinitionsPanel.test.tsx` covers the pinned-watch sentence.
- *Konfigurator nie obiecuje wykonania ani nie udaje edycji kodu* —
  `DefinitionsPanel.test.tsx::names a coded entry as code and offers no way to edit it`.

## Gaps

**Nothing has been clicked together against a running stack.** The configurator has not met
a real archive catalogue, and the seam that matters — write a rule, watch a pair with it, read
the decision back with its revision — is operator work needing the whole stack up. The shapes
are covered by tests either side of the wire; what is not covered is the operator's hands on
it. Task 7.5.

**No written rule has been backtested against `baseline_ma_cross`.** The requirement that a
clicked rule beat the floor before anybody acts on it is stated and is not yet enforced by
anything: nothing stops a watch on a rule nobody measured. Deliberately left as judgement
rather than a gate — a platform that refused to watch an unmeasured rule would also refuse
the first hour of every experiment — but it is judgement, not a check.

**`the-screen-is-mostly-refusals` has two tasks that now owe a revision.** Its 4.3 (decision
detail) and 4.5 (backtest reports) both display provenance, and both will need the revision
beside the parameter version. Noted in that change rather than done here; doing it here would
have meant two open changes editing one spec.

**`pending_setups` still aggregates over a definition rather than a revision.** Correct today
— a workbench trigger asks whether there is a setup, not whether there is one under revision
7 — and it becomes a real question the first time two revisions of one definition are watched
at once. Written down in design.md's open questions.
