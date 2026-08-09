## Context

What exists to run, measured on this machine:

| Module | Commands | Time |
|---|---|---|
| `capital-gateway` | `ruff check .`, `pytest` | ~2 s, 140 passed / 8 skipped |
| `market-data` | `ruff check .`, `pytest` | ~30 s, 435 passed / 7 skipped |
| `terminal` | `lint`, `typecheck`, `contract:check`, `test` | ~20 s, 224 passed |

Two facts shape everything below.

**`market-data`'s database tests are gated on Docker, not on a flag.** `conftest.py` skips the
`db` mark only when no Docker daemon can be found, and deliberately does *not* skip when Docker
is installed but failing — its own comment says a silent skip on a machine that was supposed to
have Docker is indistinguishable from a suite that passed. GitHub's `ubuntu-latest` has Docker,
so testcontainers starts a real PostgreSQL and the **273** `db`-marked tests run there. They are
not part of any local skip count — Docker runs on this machine, so they run here too; what skips
locally is the 7 `live` tests, which need a Capital session and stay behind `--run-live` in both
places.

**`contract:check` spans two modules.** It shells into `modules/market-data` for
`uv run python -m market_data.openapi` and pipes the result through a Node generator. A job
running it needs both toolchains.

## Goals / Non-Goals

**Goals:**

- Every check that exists runs on every pull request, without anyone remembering.
- A failure names which module and which command, without opening logs.
- What CI runs is what a developer runs — same commands, same pinned versions.

**Non-Goals:**

- Building or deploying anything. This is a check, not a pipeline.
- Caching tuned for speed. The whole suite is under a minute; a cache that goes stale silently
  costs more than it saves at this size.
- Running the `live` tests. They need a real Capital demo session and credentials, and putting
  provider credentials in CI to satisfy a green tick is a bad trade. They stay behind
  `--run-live`.
- Making the check *required*. That is a branch-protection setting on the repository, not a file
  in it — see the last decision below.

## Decisions

### One workflow, three jobs, in parallel

A job per module. They share nothing, they fail for unrelated reasons, and a broken gateway has
no business hiding whether the terminal is green. Parallel also means the wall clock is the
slowest job (`market-data`, with its containers) rather than the sum.

Rejected: one job running everything in sequence. Simpler file, worse answer — the first failure
stops the rest, so a run tells you about one problem at a time.

### `contract:check` lives in the terminal job

It is a terminal script, and the terminal job already has Node and the installed `node_modules`
that `npx openapi-typescript` needs. Giving that job `uv` as well is one extra step; giving a
separate job Node, a `pnpm install` and `uv` would duplicate the expensive half.

It runs **before** the tests, not after. If the generated contract is stale, every conclusion the
test suite reaches about the wire is drawn from an out-of-date premise — better to say so first.

### Versions are pinned, and `packageManager` becomes the single source

`pnpm` is not on this machine's PATH, `corepack` is broken under Node 25, and `node_modules` is
linked from a v11 store — so the working incantation is `npx pnpm@11`, which is knowledge living
in a review document and nowhere a tool can read. A `packageManager` field fixes that: CI reads
it through `pnpm/action-setup`, and anyone with a working corepack gets the same version without
being told.

Node is pinned to 22 rather than 25. `engines` says `>=20`, 22 is the current LTS, and the local
25 is where corepack is broken — CI is a poor place to also be the only machine on a bleeding
version.

Python comes from `uv`, which reads `requires-python = ">=3.12"` and provisions it. No separate
`setup-python`: two things deciding the interpreter version is one too many.

### The workflow runs on pull requests *and* on pushes to `main`

The pull-request trigger is the point. The push trigger is the honest complement: `main` can also
be written to directly — we did exactly that for the three archive commits — and a rule that only
watches one door is a rule that watches no doors.

### Making it *required* is a repository setting, and stays a task

A workflow produces a status; a branch-protection rule is what stops a merge without one. The
second cannot be committed to the repository, so it is written down as an explicit step for the
repo owner (`gh api` one-liner in tasks.md) rather than left implied by a green tick. Naming it
matters: a workflow that runs and is ignored looks identical, from inside the repo, to one that
gates.

## Risks / Trade-offs

- **Testcontainers in CI is the slowest and most fragile part.** It pulls a PostgreSQL image on
  every run. If it turns flaky, the answer is a `services:` container with a fixed image, not
  skipping the `db` tests — they cover the coverage/rollup logic that has been wrong twice.
- **The `db` tests have never run on Linux.** They pass on macOS against Colima or Docker Desktop.
  A first CI run is genuinely the first evidence, and may find something. That is a reason to do
  it, though it means the first green is worth more than it looks.
- **A pinned `pnpm` will drift from whatever is installed locally.** Better than the alternative,
  which is a version nobody has written down.
- **Nothing yet enforces the workflow's own correctness.** A YAML typo disables a check silently
  until someone notices no run appeared. Mitigated by watching the first run on the pull request
  this change is made in, which is named as a task.

## Migration Plan

None. Adding a workflow changes nothing about the running system; the first pull request after it
lands is where it starts having an effect.
