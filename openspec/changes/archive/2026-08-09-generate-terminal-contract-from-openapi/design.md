## Context

Proposal.md has the why. Here: only what shapes the tooling.

What exists today, measured rather than assumed:

- `app.openapi()` works with no server running and no database — FastAPI builds the document from
  the Pydantic models in `contract.py`. 27 component schemas, 25 properties carrying
  `format: date-time`.
- Every timestamp on the wire is an ISO string; every timestamp in the terminal's domain types is
  epoch seconds. `parseIsoToEpochSeconds` is applied by hand in each `map*`, and `src/data/time.ts`
  is the single place it is defined.
- Enums arrive as strings and are narrowed with `as Resolution`, `as ChunkState`, `as JobStatus`,
  `as CollectionState`. The cast is unchecked — a value the server adds and the terminal has never
  heard of passes straight through.

## Goals / Non-Goals

**Goals:**

- A field renamed, retyped or removed on the server MUST stop the terminal from compiling, rather
  than reaching an operator as a blank cell.
- Regenerating the contract MUST NOT need a running server, a database, or a network call.
- The generated artefact MUST be reviewable in a diff.

**Non-Goals:**

- Generating the `map*` functions. They are where ISO becomes epoch and where a wire string becomes
  a domain union — both required by `terminal-market-data`, both judgement calls. A generator that
  wrote them would either drop the conversion or invent a convention nobody chose.
- Generating the domain types in `src/data/types.ts`. Those are the terminal's own vocabulary and
  deliberately differ from the wire — `camelCase`, epoch seconds, narrower unions. Tying them to the
  server's shape would make every server-side rename a terminal-wide rename.
- Generating a client (paths, operations, fetch wrappers). `createArchiveSource` is hand-written on
  purpose and reads well; replacing it is a much larger change with no defect behind it.
- Runtime validation of responses. Compile-time agreement is what is missing; adding a runtime
  schema validator is a separate decision with a separate cost.

## Decisions

### Generate from `app.openapi()` dumped to a file, not from a live server

A `market-data` entry point prints the document to stdout; the terminal's script reads it. The
alternative — fetching `http://localhost:8020/openapi.json` — makes regenerating the contract
require a running stack, which means it will not be run, which is how the two copies drifted apart
in the first place.

The dumped JSON is **not** committed. It is an intermediate: the committed artefact is the
generated TypeScript, and keeping the JSON too would mean two files to keep in step for no gain.

### `openapi-typescript` rather than a hand-rolled generator

Considered writing a ~100-line script that walks `components.schemas` and emits interfaces. Rejected:
it would be new code to maintain whose entire job is a solved problem, and the corner cases
(`anyOf` with `null`, `$ref`, nested arrays, enums) are exactly where a quick script gets it subtly
wrong — which is the same class of silent error this change exists to remove.

`openapi-typescript` is a build-time-only dependency, emits one file, and needs no config. Its
output is verbose and nobody will read it, which is fine — it is read by `tsc`, not by people. The
interface to it stays one line per shape:

```ts
type RawTrackedPair = components["schemas"]["TrackedPairOut"];
```

Thirteen such lines replace thirteen hand-written interfaces, and the rest of `archive.ts` does not
change at all.

### The generated file is committed, and CI regenerates to compare

A generated file that exists only during a build cannot be reviewed, and drift becomes invisible
again — differently invisible, but no better. Committed, a contract change shows up as a diff in a
pull request next to the server change that caused it.

`contract:check` regenerates into a temporary path and compares. It fails when the committed file
is stale, which is the only failure mode worth automating: nobody forgets to *look* at a diff, they
forget to *produce* one.

### `tsc` is the drift check; no extra test is added

Once `Raw*` are aliases to the generated shapes, the existing mappers do the detecting. `raw.added_at`
against a schema that no longer has `added_at` is a type error at the line that reads it, naming
both the field and the mapper. That is a better failure than any test that could be written for it,
and it costs nothing to maintain.

Deliberately **not** added: a check that every field on the wire is consumed by some mapper. A
server growing a field the terminal ignores is normal and not an error, and a test asserting
otherwise would need an ignore-list that rots. Named here so it reads as a decision rather than an
oversight.

### Unchecked enum casts stay unchecked, for now

The generated types make `resolution` a union of the literal values the server declares, so
`as Resolution` becomes a cast between two known unions rather than from bare `string` — narrower
than today, and a resolution added on the server but not in the terminal becomes a visible type
error. A server value that is not in the union *at runtime* still passes; closing that needs runtime
validation, which is a Non-Goal above.

## Risks / Trade-offs

- **One more devDependency in the terminal.** Weighed against ~250 lines of hand-maintained
  transcription and a silent failure mode. Build-time only, never shipped.
- **The generated file is large and noisy in diffs.** Real, and the point: a noisy diff on a
  contract change is the signal. Reviewers read the `archive.ts` side, which stays small.
- **A stale committed file passes locally until CI runs.** `contract:check` runs in the same script
  as lint and typecheck so it is one command locally too, but nothing forces a developer to run it
  before pushing. Accepted — the failure is loud and early, which is the whole improvement.
- **Regeneration needs the `market-data` Python environment.** A terminal-only checkout cannot
  regenerate. Acceptable in a monorepo where both modules are present; noted because it makes the
  terminal's build no longer self-contained if that ever stops being true.

## Migration Plan

No runtime change, no schema change, no data migration. The generated file is added, `Raw*` become
aliases in one commit, and the wire shapes are byte-for-byte what they were — provable by the fact
that no `map*` body and no test needs to change.
