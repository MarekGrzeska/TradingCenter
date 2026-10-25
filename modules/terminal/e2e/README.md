# End-to-end tests

Playwright against a live, isolated stack: the terminal on 15173, a workbench on 18030 and PostgreSQL on 55442, none of
which is the dev stack's. No model is paid for: every OpenAI address and key in `workbench.env` leads nowhere. Plan and
reasoning: `docs/playwright-e2e-propozycja.html`.

Phase 0 runs by hand; phase 1 folds these steps into one `pnpm e2e`.

```bash
# from modules/terminal
docker compose -f e2e/compose.e2e.yaml up -d --wait
# the workbench, from e2e/ so modules/workbench/.env is never read; workbench.env becomes its environment
#   (cwd e2e/, PYTHONPATH=../workbench, uvicorn --app-dir ../../workbench workbench.app:app --port 18030)
PYTHONPATH=../workbench uv run --project ../workbench python e2e/seed.py
pnpm exec playwright install chromium   # once per machine
pnpm exec playwright test
docker compose -f e2e/compose.e2e.yaml down
```
