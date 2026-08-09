## Verdict

Shipped. `app.py` went from 773 lines to **190** and now holds only assembly: the lifespan,
the error handling every route shares, and five routers mounted onto it. The fifteen routes
live in `routers/` split by area — `meta`, `candles`, `pairs`, `jobs`, `stream` — the
market-status cache is an object on `app.state` instead of a module-level dict, and the
domain logic that sat in the route file moved next to what it talks to.

**The published document is byte-for-byte identical.** Dumped before the first edit, dumped
after the last, `diff` reports nothing — and the terminal's generated contract, which landed
an hour earlier in `generate-terminal-contract-from-openapi`, agrees. That ordering was
argued for in both proposals and it earned itself here: this is exactly the kind of
rearranging where `operationId` or a tag moves unnoticed.

Knowingly incomplete: task 5.4, a manual pass on a running stack, is left for the operator.
A refactor that promises no behaviour change deserves confirming by behaviour, and the test
suite is not that.

## Verified

- `uv run ruff check .` → `All checks passed!`
- `uv run pytest -q` → `435 passed, 7 skipped`, twice in a row (was 423 before; +12 from the
  new `tests/test_market_status.py`)
- OpenAPI, the load-bearing check:
  `diff openapi-before.json openapi-after.json` → no output. 11 paths, 31 components, same
  bytes.
- `cd modules/terminal && pnpm contract:check` → `Contract is up to date.` — a second,
  independent witness to the same fact, arrived at through a different tool
- `wc -l market_data/app.py` → 190

## Findings

| Severity | Where | Finding | Status |
|---|---|---|---|
| Medium | `market_status.py` | The design said `MarketStatus` would be built from a `GatewayInstruments`. It cannot be, without changing behaviour: every route in this module resolves `app.state.instruments` **per request**, which is what lets a test swap the gateway after the application exists — four tests in `test_app.py` do exactly that. Capturing the gateway at construction would have moved when that dependency is resolved, inside a refactor whose whole promise is that nothing moves. | Changed — `MarketStatus` owns the memory and takes the gateway per call. The odd signature is the honest one |
| Low | `tests/test_app.py` | Two edits were forced beyond deleting the cache fixture, and by the rule set in tasks.md 4.2 both are reported rather than quietly made. **One:** the `api` fixture bypasses `lifespan` and hand-builds `app.state`, so it now supplies `MarketStatus()` — the same category as the six entries it already supplied, and a net loss of eight lines against the autouse fixture it replaces. **Two:** four tests import `candle_feed` from `market_data.app`, and it lives in `market_data.routers.stream` now. Neither touched an assertion. | Accepted — the contract under test is unchanged, which the OpenAPI diff proves independently |
| Low | `tests/test_jobs_runner.py` | `test_the_runner_claims_and_settles_a_pending_chunk` failed once during this work and passed in isolation immediately after, then passed in two consecutive full runs. It drives a background worker against a real database with a five-second idle poll, so a timing flake is the likely reading — but it is recorded rather than dismissed, because "it passed the second time" is how a real intermittent failure gets buried. | Not fixed — named, not diagnosed |

## Deviations from design.md

- **`MarketStatus`'s constructor**, as above. The design's sketch took `instruments`; the
  built one does not.
- **It is read through `request.app.state`, not `Depends`.** The design said "read through a
  `Depends` like `pool` and `hub` already are". In the one route that uses it, the two lines
  either side already reach for `app.state.instruments` and `app.state.ingest` directly; a
  dependency provider for one of three neighbours would be an inconsistency wearing the
  costume of an improvement. Corrected in tasks.md rather than left as a tick that claims
  more than was done.
- Everything else held: five routers by area, tags untouched, `deps.py` with only the two
  providers, `contract.py` gaining `FillOut.of` and `TrackedPairOut.of` in the shape
  `PairEstimateOut.of` already established.

## How the move was made, since it matters for reviewing it

The route bodies were **extracted by line range, not retyped**. A refactor that must change
nothing is a poor place for transcription, and the mechanical cut means the diff for each
route is a pure move. What the extraction could not carry — five names that were module
globals or private helpers — surfaced as five `F821` errors from `ruff` and were resolved
one at a time. Unused imports in each new file were removed by `ruff --fix` rather than
guessed at.

That is also why the OpenAPI diff is worth as much as it is: if a body had been retyped,
"identical schema" would say nothing about the body. Since the bodies moved untouched, the
schema check and the 435 tests are covering different things.

## Gaps

- **Task 5.4** (manual pass on a running stack) is deferred to the operator: the wizard, a
  job, `Data History`, a deletion, and a live chart. Every route was moved, including the
  WebSocket, and no test drives a real gateway.
- **`app.py` still owns `candle_sink`**, which is arguably ingest's business rather than the
  HTTP layer's. Left alone deliberately: it is constructed in `lifespan` from `pool` and
  `hub`, so moving it would be a second refactor riding along inside this one. Named so the
  190 lines are not mistaken for "nothing left to do".
- **`tracking.py` grew** by `decide_late_pairs` (389 → ~430 lines). It is the right home —
  the function reads `CollectionState` and calls `collection_state`, both of which live
  there — but the file was already on the long side, and this change deliberately did not
  split it (design.md, Non-Goals).
