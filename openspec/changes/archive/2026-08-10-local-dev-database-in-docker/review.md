## Verdict

Local development runs against the `compose.yaml` container again and production is
untouched — the connection mode is chosen by the presence of `DATABASE_USER`, and its
absence confines the module to loopback. The guard is stronger than the one it replaced:
the old check was a grep for a database name in `dev.sh` and could not see an ambient
`az login` credential reaching production as the Postgres administrator; the new one lives
in `config.py` and refuses at startup. Two things a later reader should not mistake for
oversights: `db.py` was deliberately not touched (its identity-less path predates this
change and the test suite has always used it), and the loopback rule in `scripts/dev.sh` /
`dev.ps1` has no automated test — it duplicates a rule the module enforces on its own, and
exists only to fail earlier and name the file to fix.

## Verified

- `uv run pytest -q` in `modules/market-data` — **520 passed, 7 skipped** (the 7 are
  `live`, which need a Capital session and stay behind `--run-live`). The `db`-marked
  tests ran: the daemon was present, so testcontainers started a real PostgreSQL.
- `uv run ruff check .` — All checks passed.
- `terraform fmt -check` in `infra/` — clean.
- `openspec validate local-dev-database-in-docker --strict` — valid.
- End-to-end on a fresh container, outside the suite: `docker compose up -d --wait db`
  reached healthy, `uv run alembic upgrade head` migrated in local mode, and
  `psql \dt` listed all 8 tables. This is what proves the local mode actually connects;
  the unit tests only prove the configuration is accepted.
- `terraform apply` (operator, locally): 4 destroys — the dev application, its password,
  its service principal and `market_data_dev`. A following `plan -detailed-exitcode`
  returned 0, and `az ad app list` / `az ad sp list` return nothing for the dev name.

## Findings

| Severity | Where | Finding | Status |
|---|---|---|---|
| Low | `market_data/config.py:140` | `_connection_mode_is_coherent` was annotated `-> "Settings"` with the quotes, which `ruff` rejects (UP037) under `from __future__ import annotations` | FIXED before commit, in `42b3143` |
| Info | `infra/entra.tf`, `infra/database.tf` | Removing these resources DROPs `market_data_dev` on apply. Dev data is disposable by definition, but the plan's `destroy` deserved to be visible rather than discovered | FIXED — comment left at the removal site, and the PR body says it |

No defects found in the diff beyond those. The change is small in code and large in
documentation, and the code half is mostly the deletion of a mode.

## Spec coverage

| Requirement / Scenario | Proven by |
|---|---|
| **Połączenie z bazą jest szyfrowane** | |
| Konfiguracja nie wymusza szyfrowania | `tests/test_config.py::test_a_database_url_that_does_not_require_tls_refuses_to_start` (4 parametrisations) |
| Serwer nie oferuje szyfrowania | — no test; see Gaps |
| Baza lokalna bez szyfrowania | `tests/test_config.py::test_local_mode_does_not_require_tls` |
| **Moduł przedstawia się tożsamością, nie hasłem** | |
| Poświadczenia nie da się uzyskać | `tests/test_db.py::test_token_provider_wraps_a_credential_failure` |
| Poświadczenie w URL obok tożsamości | `tests/test_config.py::test_a_database_url_with_a_credential_refuses_to_start` (2 parametrisations) |
| **Praca bez tożsamości nie wychodzi poza maszynę** | |
| Baza lokalna na haśle | `tests/test_config.py::test_no_database_user_with_a_loopback_url_is_local_mode`, and `test_a_blank_database_user_means_local_mode_not_a_role_named_blank` for the `DATABASE_USER=` spelling |
| Host zdalny bez tożsamości | `tests/test_config.py::test_no_database_user_with_a_remote_host_refuses_to_start` (2 parametrisations: the Azure server, and an arbitrary remote host with TLS) |
| Narzędzie deweloperskie odmawia wcześniej | — no automated test; see Gaps |

## Gaps

**„Serwer nie oferuje szyfrowania" has no test, and this predates the change.** It
describes what happens when a server refuses a TLS handshake, which needs a server that
refuses one — the testcontainers PostgreSQL accepts. Carried forward unchanged: this
change narrowed the requirement's scope to remote databases but did not touch this
scenario's testability.

**„Narzędzie deweloperskie odmawia wcześniej" is verified by hand, not by a test.** The
host-extraction expression in `scripts/dev.sh` was exercised against four URL shapes
(loopback with `user:pass@`, the Azure host with a query string, a host with no port, and
a `postgresql+asyncpg://` scheme) and returned the right host each time — but that was a
terminal session, not something CI repeats. The scenario's real protection is the module's
own refusal, which is tested; the script only fails earlier and more legibly. A shell test
here would be the second test of one rule, which is why there is not one.

**`scripts/dev.ps1` was not run.** No PowerShell on the machine this was written on. Its
edits mirror `dev.sh` line for line and its syntax is unverified.
