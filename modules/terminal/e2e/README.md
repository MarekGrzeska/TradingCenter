# End-to-end tests

Playwright against a live, isolated stack: the terminal on 15173, a workbench on 18030 and PostgreSQL on 55442 in memory,
none of which is the dev stack's, so both run at once. No model is paid for: every OpenAI address and key in
`workbench.env` leads nowhere, and `scripts/e2e.py` passes nothing from your shell but what finds the tools. Plan and
reasoning: `docs/playwright-e2e-propozycja.html`.

```bash
pnpm exec playwright install chromium   # once per machine
pnpm e2e                                # start, seed, test, tear down (about a minute)
pnpm e2e -- -g BT-07                    # anything after `--` goes to `playwright test`
pnpm e2e -- --keep                      # leave the stack up, then `pnpm exec playwright test --ui`
```

The workbench's output is in `e2e/workbench.log`, a failed test's trace in `test-results/`.

- **One path per feature.** A rule's variants belong in pytest or vitest; a test here proves the state crosses the real
  stack and reaches the screen.
- **Set up through REST, check on screen** (`support.ts`). Each test makes its own strategy with a unique name.
- **Ids match the manual scenarios**: ST-01 here covers S-01/S-03 in `docs/strategie-scenariusze-testowe.html`.
- **The agent is a scenario** (`agent-scenario.json`, `AGENT_PROVIDER=sim`): a message matching a rule gets that
  rule's tool calls and text, with named groups filled in — `E2E szkic 7` drafts strategy 7. The tools are real.
- The seed (`seed.py`) is thirty weekdays of US100 minutes to today's UTC midnight and an operator's cost profile.
