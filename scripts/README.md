# scripts

Repository tooling: `dev.py` starts the whole stack locally, `deploy_probe.py` is the step
every `deploy-*.yml` ends in. Both were shell before 18 August 2026 — `dev.sh` plus
`dev.ps1`, and a loop pasted into seven workflows — and both are defences that had no test
of their failure mode, which is why they now live in a directory with a `pytest`.

`dev.sh` and `dev.ps1` still work; they are wrappers that pass their arguments here.

`enable_youtube_prod.py` is the operator's half of switching the YouTube archive on in production: it hands the
`youtube` database to the workbench's role and writes the two provider keys to Key Vault from the local `.env`, never
printing them. A dry run unless `--apply`; the order it belongs in is in its docstring and `infra/variables.tf`.

```
uv run pytest         # unit tests — no Docker, no Azure, no network
uv run ruff check .
uv run pyright
```

`uv run python dev.py --help` lists the flags. The service table lives at the top of
`dev.py`: one row per service, with the reason its position in the order is what it is.
