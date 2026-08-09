## Verdict

Shipped. The terminal's thirteen hand-written `Raw*` interfaces are gone; twelve one-line
aliases into `src/data/contract.generated.ts` replace them, and that file is produced from
`market-data`'s own OpenAPI document by `pnpm contract:generate`. A renamed field now stops the
terminal compiling on the line that reads it — verified by doing exactly that and reverting.

Two things the design did not anticipate, both found by doing the work, both making the change
larger than proposed and better for it. They are the substance of this review and are written up
as findings below rather than folded into the summary.

Knowingly incomplete: `contract:check` is not wired into CI, because this repository has no CI —
there is no `.github/workflows`. The script exists and runs locally; hooking it up is a task for
whoever adds the first pipeline, and it is named in Gaps rather than quietly assumed.

## Verified

- `cd modules/market-data && uv run pytest -q` → `423 passed, 7 skipped` (was 415; +8 from the new
  `tests/test_openapi.py`)
- `cd modules/market-data && uv run ruff check .` → `All checks passed!`
- `cd modules/terminal && pnpm lint && pnpm typecheck && pnpm contract:check` → clean, `Contract is
  up to date.`
- `cd modules/terminal && pnpm test` → `221 passed`, **with no edit to any test file** — the
  acceptance criterion from tasks.md 3.3, and the evidence that nothing about the wire moved
- The guard, exercised rather than reasoned about:
  - renamed `ChunkOut.candles_written` → `candles_stored`, regenerated, and `tsc` answered
    `archive.ts(113,25): Property 'candles_written' does not exist` — the mapper and the field, by
    name. Reverted.
  - changed `contract.py` **without** regenerating and `contract:check` exited 1 with the message
    naming `contract:generate`. Reverted.

## Findings

| Severity | Where | Finding | Status |
|---|---|---|---|
| High | `market_data/openapi.py`, `app.py` | The subscription's messages were in no schema at all. FastAPI documents routes, and a WebSocket has none — so `Snapshot`, `CandleChange` and `Candle` appeared in neither `paths` nor `components`. Generating from the document as-is would have left `RawStreamCandle` as the one shape still copied by hand, in the most-read part of the whole contract: a chart sees every candle through it. | Fixed — `add_stream_messages` hangs the models on the document, and the app publishes the augmented one so `/openapi.json` and the dump are the same bytes |
| High | `market_data/openapi.py` | The published schema described this module's responses inaccurately. Pydantic leaves a field with a default out of `required`, which is right for something a caller sends and untrue for something the module answers with — FastAPI serialises a response model whole, so `TrackedPairOut` always carries `earliest_candle`, `null` when there is none. Generating off the raw reading produced **18 type errors**, every one demanding `undefined` handling for a case that cannot occur. | Fixed — `require_response_fields` marks response properties required; request models keep Pydantic's reading, told apart by reachability from a `requestBody` rather than by a hand-kept list that would rot |
| Low | `src/data/archive.ts` | `RawTrackedPairResult` became unused. It existed only so `RawTrackPairsResult` could refer to it, and that relationship now lives inside the generated types. | Removed — thirteen interfaces became twelve aliases |
| Low | tooling, `modules/terminal` | The module is a pnpm workspace, but `pnpm` is not on PATH and `corepack` is broken under Node 25 (`ERR_VM_DYNAMIC_IMPORT_CALLBACK_MISSING`). `npm install` fails outright, and `npx pnpm@10` refuses because `node_modules` is linked from a **v11** store. `npx pnpm@11` works. | Not fixed — an environment fact, not a defect in this change. Worth a `packageManager` field in `package.json` so the version is not folklore |

The first two findings are the same defect wearing two hats: the schema was treated as documentation
for people, and documentation for people tolerates being approximately right. The moment something
generates from it, "approximately" becomes eighteen compile errors and one silently missing shape.
Both fixes make the published document more truthful about what the module actually sends, which is
worth having regardless of who reads it.

## Deviations from design.md

- **`openapi-typescript` was kept**, as designed, and the one-line-alias shape held: `type RawChunk =
  Wire["ChunkOut"]`. No hand-rolled generator was written.
- **The dumped JSON is not committed**, as designed. The generated TypeScript is.
- **Scope grew by two server-side changes** (`add_stream_messages`, `require_response_fields`) that
  the proposal did not mention — it said market-data would get "a small entry point printing
  `app.openapi()`" and no more. Both alter the *published document*, though neither alters a route,
  a model, a response body or a status code, so no behaviour a client can observe has changed. The
  proposal's claim that market-data would be untouched apart from the entry point did not survive
  contact with the WebSocket, and this paragraph exists so the diff does not read as scope creep
  nobody declared.

## Gaps

- **`contract:check` runs nowhere automatically.** No CI exists in this repository. Until one does,
  a stale generated file is caught only by someone running the command, which is weaker than the
  design claimed ("fails when the committed file is stale" is true; "and something runs it" is not
  yet).
- **Runtime values are still unchecked.** The generated types narrow `resolution` and the state
  enums to the literals the server declares, so a value the terminal has never heard of is now a
  visible type error at build time — but a value arriving at *runtime* outside the union still
  passes through `as Resolution`. Runtime validation was a Non-Goal and remains one.
- **A terminal-only checkout cannot regenerate**, since the script shells into `market-data`'s Python
  environment. Fine in this monorepo, named in design.md's Risks, unchanged.
