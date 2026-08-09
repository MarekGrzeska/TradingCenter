## Verdict

Shipped. `.github/workflows/checks.yml` runs three jobs in parallel on every pull request to
`main` and every push to it, running the same commands a developer runs. The whole run takes
**73 seconds** wall clock.

It was proved both ways, which is the part worth reading. Green is easy to get and easy to
mistake for working; the run that matters is the one where three deliberate breaks each turned
the right job red on the right step.

Knowingly incomplete: branch protection. A workflow produces a status, and only a repository
setting turns that into a merge that cannot happen. It is task 4 and it belongs to whoever owns
the repository.

## Verified

Locally, the same commands in the same order: `capital-gateway` 140 passed / 8 skipped,
`market-data` 435 passed / 7 skipped, `terminal` 224 passed with `contract:check` clean.

On the runner, [run 31309352112](https://github.com/MarekGrzeska/TradingCenter/actions/runs/31309352112):

| Job | Result | Time |
|---|---|---|
| `capital-gateway` | success | 16 s |
| `market-data` | success | 47 s |
| `terminal` | success | 73 s |

The terminal job's steps all ran in the intended order — `contract:check`, then `lint`,
`typecheck`, `test`.

**The 273 database tests passed on Linux at the first attempt.** They had only ever run on macOS
against Colima or Docker Desktop; testcontainers started PostgreSQL on `ubuntu-latest` with no
adjustment. design.md called this the risk most likely to bite, and it did not.

And red, [run 31309449497](https://github.com/MarekGrzeska/TradingCenter/actions/runs/31309449497)
— one deliberate break of each kind, in one commit, reverted in the next:

| Job | Broke on | What was broken |
|---|---|---|
| `capital-gateway` | `uv run ruff check .` | an unused import |
| `market-data` | `uv run pytest -q` | a flipped assertion |
| `terminal` | `pnpm contract:check` | a hand-edited line in the generated contract |

Three jobs, three different kinds of failure, each naming its own step. The terminal's later
steps were skipped, which is the intended shape: a stale contract stops the suite rather than
letting it draw conclusions from an out-of-date premise.

## Findings

| Severity | Where | Finding | Status |
|---|---|---|---|
| High | `checks.yml` | The first run failed before installing anything: `pnpm/action-setup` looks for `packageManager` in the repository root, and `defaults.run.working-directory` does not apply to actions — only to `run` steps. There is no root `package.json`, so it had nothing to read. | Fixed — `package_json_file: modules/terminal/package.json`, with the reason in a comment so the next person does not re-derive it |
| Medium | proposal, design, tasks, workflow comment | I wrote that the 7 tests skipping locally were the database ones and that CI would finally run them. **Both halves were wrong.** The 7 are the `live` tests, which need a Capital session and skip in both places; the `db` tests never appeared in a local skip count because Docker runs on this machine. The real figure is 273, and CI ran all of them. | Fixed in every place I had repeated it. The claim was load-bearing — it was the stated reason for not using a `services:` container — so leaving it would have made a correct decision rest on a false premise |
| Low | procedure | While confirming the red run I read the wrong one: `gh run list --limit 1` returned the run for the *previous* push, which `concurrency` then cancelled. Reported `capital-gateway: success` for a commit that could not have passed. Caught by comparing `headSha` against local `HEAD`. | Not a repository defect — a note that a run must be matched by SHA, never by recency |

The second finding is the one I would want a reader to weigh. The workflow is right, but the
paragraph explaining *why* it is right was wrong for its whole life until the first run
contradicted it, and nothing except running it would have.

## Deviations from design.md

- **`pnpm/action-setup` needed `package_json_file`**, which the design did not anticipate. The
  intent — one pinned version that CI and a developer both read — is unchanged; it just needs
  the path spelled out.
- Everything else held: three parallel jobs, `contract:check` before the tests, `uv` providing
  the interpreter, Node pinned to 22, `permissions: contents: read`.

## Gaps

- **Branch protection is not on.** Until it is, this workflow is a status nobody is obliged to
  read, and from inside the repository that is indistinguishable from one that gates. The
  `gh api` invocation is written out in tasks.md 4.1.
- **The `live` tests still never run anywhere automatically.** Deliberate — they need provider
  credentials — but it means the gateway's contract with the real Capital API is checked only
  when somebody remembers to pass `--run-live`, which is the same weakness this change exists
  to remove, just moved somewhere smaller.
- **Nothing checks the workflow itself.** A YAML typo disables a job silently; the only reason
  the `package_json_file` bug was caught in minutes is that watching the first run was a task.
  A future edit gets no such attention by default.
