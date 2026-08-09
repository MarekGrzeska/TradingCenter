## Verdict

The platform is built and the module-level work behind it is sound: `capital-gateway` refuses every
unauthenticated call, `market-data` reaches both its database and its upstream on an identity rather
than a password, and the terminal now talks to one origin instead of two. 487 market-data tests and
224 terminal tests pass, and the delta specs are covered by real tests almost everywhere.

**Update, same day:** all eight items under Findings are now fixed — see the Status column and the
note after the table. The bootstrap Terraform state's leaked storage-account keys are the one fix
applied live rather than only in source: `shared_access_key_enabled` is now `false` on
`sttradingcenterstate`, applied via `terraform apply` in `infra/bootstrap/` and confirmed with
`az storage account show` (`allowSharedKeyAccess: false`). The keys are still physically present in
the committed state file — Azure's `ListKeys` is a control-plane call independent of this setting —
but are now permanently unusable for authentication, which was the fix this finding actually called
for. The three deploy-breaking High findings and the four Medium findings are code fixes, verified by
re-running the same commands as the first pass (see Verified) but **not yet committed** — this file
was updated in the same working-tree state as the fixes, ahead of that commit.

**Second update:** pushing the branch ran the pipeline for the first time, which produced four more
findings — recorded under Findings in their own table. One of them is worse than anything in the
original eight: an apply from CI would have destroyed the operator's Key Vault access policy and
recreated it pointing at the CI principal. It was invisible to reading because it depends on which
identity runs Terraform, and until that push only the operator ever had. `terraform apply` is now
the operator's job and CI plans only.

What a later reader should not mistake for oversight: Easy Auth on market-data (`Return401`) with a
terminal that sends no token is deliberate and documented — the deployed pair is known to be
non-functional until the browser-side 401 handling lands.

## Verified

Run locally, the same commands and the same order as `.github/workflows/checks.yml`, at `e2c3e67`:

| Module | Command | Result |
|---|---|---|
| `capital-gateway` | `uv run ruff check .` | All checks passed |
| `capital-gateway` | `uv run pytest -q` | **1 failed**, 153 passed, 8 skipped |
| `market-data` | `uv run ruff check .` | All checks passed |
| `market-data` | `uv run pytest -q` | 487 passed, 7 skipped, 27.75 s |
| `terminal` | `pnpm contract:check` | Contract is up to date |
| `terminal` | `pnpm lint` / `pnpm typecheck` | clean |
| `terminal` | `pnpm test` | 224 passed, 16 files, 10.32 s |

The market-data suite ran its database tests against testcontainers on this machine; the 7 skips are
the `live` tests, as before.

**`capital-gateway` is not green.** `tests/test_access_control.py::test_start_without_a_gateway_key_is_refused`
fails with `DID NOT RAISE ValueError`. It is not a flake and not environment noise in the dismissible
sense — see finding 5. It passes on CI and fails on any machine that has a `.env`, which is every
developer machine, so `checks.yml` will stay green over it.

The infrastructure itself was not applied or deployed from this review — findings 1-4 are read from
the Terraform and workflow sources, not from a failed run. Task 7.4 records why no deploy has
happened yet (the federated credential accepts only `ref:refs/heads/main`).

## Re-verified after fixes

Same commands, same order, run against the uncommitted working tree that carries the fixes below —
not a fresh `e2c3e67`, since nothing has landed as a commit yet:

| Module | Command | Result |
|---|---|---|
| `capital-gateway` | `uv run ruff check .` | All checks passed |
| `capital-gateway` | `uv run pytest -q` | 154 passed, 8 skipped — run with the developer's own `.env` present, the exact condition finding 5 was about |
| `market-data` | `uv run ruff check .` | All checks passed |
| `market-data` | `uv run pytest -q` | 487 passed, 7 skipped, 26.49 s |
| `infra` | `terraform fmt -check -recursive` | clean |
| `infra` | `terraform validate` | Success |
| `terminal` | `pnpm contract:check` | Contract is up to date |
| `terminal` | `pnpm lint` / `pnpm typecheck` | clean |
| `terminal` | `pnpm test` | 224 passed, 16 files, 9.82 s |

`capital-gateway` is green outright now, including on a machine with a `.env` — the failure finding 5
described is gone rather than newly masked. The infra apply itself is covered separately, in the
Verdict update above and finding 1's row.

## Findings

| Severity | Where | Finding | Status |
|---|---|---|---|
| Critical | `infra/bootstrap/terraform.tfstate:115-123`, `187-195` | The committed bootstrap state carries the `sttradingcenterstate` storage account's **live primary and secondary access keys** and full connection strings in plaintext. `shared_access_key_enabled` is `true` in the same state, so they are usable. `.gitignore:84-85` commits the file on purpose, on the stated grounds that "it carries nothing sensitive" — `azurerm_storage_account` always pulls the keys into state, so that premise was never true. The branch is **not pushed** and the repository is private, so exposure is still local and the history can be rewritten cleanly. | **Fixed** — `shared_access_key_enabled = false` added (`infra/bootstrap/main.tf:51`) and **applied live**: `terraform apply` ran against the real storage account, `az storage account show` confirms `allowSharedKeyAccess: false`. The keys in the committed state are now permanently inert rather than scrubbed — see the Verdict update. `.gitignore`'s comment corrected to say so |
| High | `infra/app-service.tf:170` | The market-data App Service sets neither `DATABASE_URL` nor `DATABASE_USER`, and `market_data.config.Settings` declares both as required `str` with no default (`config.py:54-55`). `grep -rn "DATABASE_URL\|DATABASE_USER" infra/` returns nothing. The first deploy restart-loops on a pydantic `ValidationError`. | **Fixed** — `infra/app-service.tf:181-182`: `DATABASE_URL` built from the Postgres server's own `fqdn` and the `market_data` database resource, `sslmode=require`, no credential; `DATABASE_USER` set to `local.market_data_app_name`, matching the role 5.7 already created for this identity. `terraform validate` clean. Not yet applied — lands with the next `terraform apply` on `main` |
| High | `.github/workflows/deploy-terminal.yml:24` | `pull_requests: write` is not a valid permission scope — it is `pull-requests`, spelled correctly in `terraform.yml`. GitHub rejects the whole workflow file, so the terminal never deploys at all; the PR comment is not the only casualty. | **Fixed** — `pull-requests: write` (`deploy-terminal.yml:24`) |
| High | `.github/workflows/deploy-terminal.yml:62` | `VITE_ARCHIVE_WS` is set to `wss://.../ws/candles`, but `archive.ts:323` appends `/candles` to the base it is given. Production would dial `wss://.../ws/candles/candles?...` and never connect. `.env.example:17` has the correct shape — the base is `/archive-api/ws`. | **Fixed** — base trimmed to `wss://app-tradingcenter-market-data.azurewebsites.net/ws` (`deploy-terminal.yml:62`), matching `.env.example`'s shape |
| Medium | `modules/capital-gateway/tests/test_access_control.py:141` | `test_start_without_a_gateway_key_is_refused` deletes the env var but `Settings` reads `env_file=".env"` (`config.py:42`), so a developer's `.env` still satisfies it and the test fails locally while passing on CI. It also inverts the guarantee: the test is green exactly where the misconfiguration cannot happen and red where it can. `Settings(_env_file=None)` fixes both halves. | **Fixed** — `Settings(_env_file=None)` (`test_access_control.py:150`), re-verified green on a machine with a real `.env` (see Re-verified after fixes) |
| Medium | `modules/capital-gateway/capital_gateway/app.py:118` | `/docs` and `/openapi.json` are deliberately served off production, but `_UNAUTHENTICATED_PATHS` exempts only `/` (`app.py:78`). A browser sends no `X-Gateway-Key`, so both answer `401` — the docs URL both dev scripts print is dead. The spec scenario "Odpytanie o schemat poza produkcją" is met only by a caller that already holds the key. | **Fixed** — `_UNAUTHENTICATED_PATHS` now `{"/", "/docs", "/openapi.json"}` (`app.py:82`); harmless in production since `docs_url`/`openapi_url` are `None` there, so the routes don't exist regardless of the exemption. No new test added — the existing `test_docs_are_published_off_production` still sends the key and still passes |
| Medium | `modules/capital-gateway/capital_gateway/app.py:96`, `:346` | `hmac.compare_digest` on `str` raises `TypeError` for non-ASCII input. Headers are latin-1 decoded, so any high byte in `X-Gateway-Key` produces an unhandled `500` instead of `401` — reachable with no credential, and it feeds the `alert-gateway-http-5xx` rule. Compare on bytes instead. | **Fixed** — both call sites now compare `.encode()`d bytes (`app.py:103` and `:355`) |
| Medium | `.github/workflows/terraform.yml:69` | `${{ steps.plan.outputs.stdout }}` is interpolated into a JS template literal inside `actions/github-script`. A backtick or `${` in plan output breaks the step or executes as script, in a job holding `pull-requests: write` and `id-token: write`. Pass the plan through `env:` and read `process.env` in the script. | **Fixed** — plan output passed via `env: PLAN` and read as `process.env.PLAN` (`terraform.yml:65-75`) |

### Found by running the pipeline, after the table above

The eight findings above came from reading. Pushing the branch ran `terraform.yml` for the
first time and produced four more, listed here rather than folded into the table because
they were found a different way and none of them is visible in the source alone.

| Severity | Where | Finding | Status |
|---|---|---|---|
| Critical | `infra/key-vault.tf:37`, `infra/github-oidc.tf:110` | Both took their principal from `data.azurerm_client_config.current.object_id` — *whoever is running Terraform*. Locally that is the operator; in Actions it is the CI service principal. CI's plan read `object_id ... -> ... # forces replacement` on `azurerm_key_vault_access_policy.operator`: an apply from CI would have **destroyed the operator's own Key Vault access policy and recreated it pointing at CI**, locking the only person who writes secret values out of the vault. `azurerm_role_assignment.operator_tfstate` had the same shape. | **Fixed** — both read an explicit `var.operator_object_id`; it resolves to the same identity, so the local plan shows neither resource at all |
| High | `infra/github-oidc.tf` (the whole root) | The CI principal has **no Microsoft Graph access**, so `terraform plan` 403s (`Authorization_RequestDenied`) refreshing all three `azuread_application` resources. This root has never been plannable, let alone applyable, from CI. | **Fixed** — `Application.Read.All` granted via `azuread_app_role_assignment`; read, not write, because CI no longer applies |
| High | `infra/github-oidc.tf:91` | `data "azurerm_storage_account" "tfstate"` is a management-plane GET, and CI holds only `Storage Blob Data Contributor` there — a data-plane role that does not include `Microsoft.Storage/storageAccounts/read`. 403 on every plan. | **Fixed** — the id is composed from the names `bootstrap/` already hardcodes, so nothing is asked of Azure |
| Medium | `.github/workflows/terraform.yml` | The `apply` job could never have worked: applying this root needs directory write, which CI does not have and should not be given for a platform one person operates. | **Fixed** — the `apply` job is removed and `terraform apply` is the operator's, run locally. The three application deploy workflows still authenticate through OIDC, unchanged |

A separate OIDC failure preceded all four and is worth recording because the symptom
misleads: GitHub has migrated this repository to **immutable subject claims**, so the
token presents `repo:MarekGrzeska@48219464/TradingCenter@1326647472:...` and matches
neither name-based federated credential. Entra refuses with `AADSTS700213`, but the
provider retries first, so it surfaces as `terraform init` sitting on "Initializing the
backend..." for seven and a half minutes before failing. Fixed by registering both
subject forms (`infra/github-oidc.tf`). This is what task 7.4 was actually blocked on —
its recorded reason (the `ref:refs/heads/main` filter) was not the whole story.

Finding 1 was the one that decided whether this branch could be pushed as it stood, and it no longer
blocks that: `shared_access_key_enabled = false` is live on the storage account, applied the same way
any other change to this root would be, and confirmed independently with `az storage account show`
rather than taken on the plan's word. The other seven are ordinary defects, fixed the same pass — see
the Status column above and Re-verified after fixes.

## Spec coverage

| Requirement / Scenario | Proven by |
|---|---|
| **capital-access-control** | |
| Każde wywołanie niesie poświadczenie / bez poświadczenia | `test_access_control.py::test_a_request_without_the_header_is_refused` + `::test_neither_refusal_reaches_the_provider` (asserts the provider route count is 0) |
| …/ z nieuznanym poświadczeniem | `::test_a_request_with_the_wrong_key_is_refused`; the "nie rozróżnia nieistniejącego od błędnego" clause is **not** asserted — both cases are checked for `401` separately, never compared |
| …/ zestawienie WebSocketa bez poświadczenia | `::test_a_websocket_without_the_header_is_closed`, `::test_a_websocket_with_the_wrong_key_is_closed`; "nie zapisuje konsumenta do rozgłaszania" is **not** asserted against the hub |
| Bez skonfigurowanego poświadczenia moduł nie wstaje / start bez konfiguracji | `::test_start_without_a_gateway_key_is_refused` — fixed by finding 5, now green including with a developer `.env` present. "Nie zaczyna nasłuchiwać na żadnym porcie" is still not covered |
| Sonda zdrowia jest jedynym wyjątkiem / platforma odpytuje sondę | `::test_the_health_probe_needs_no_key`, `::test_the_health_probe_names_nothing_sensitive` (asserts the body is exactly `{service, status}`) |
| Na produkcji moduł nie publikuje API / na produkcji | `::test_docs_are_absent_in_production` — both `/docs` and `/openapi.json` answer `404` |
| …/ poza produkcją | `::test_docs_are_published_off_production` — the test still sends the key, but finding 6's fix means a caller without one now reaches the schema too, which the scenario actually asks for. No test added for the no-key case |
| Poświadczenie nie trafia do logów / odrzucone żądanie w logu | `::test_a_refusal_does_not_echo_the_key_back` asserts the **response body**, not the log. The scenario is about the log record and nothing reads one |
| **market-data-upstream-access** | |
| Ruch do gatewaya niesie poświadczenie / REST | `test_gateway_history.py::test_the_shared_client_carries_the_caller_key_on_every_request` |
| …/ WebSocket | `test_gateway_stream.py::test_the_handshake_carries_the_caller_key` |
| Bez poświadczenia moduł nie wstaje | `test_config.py::test_a_missing_gateway_api_key_names_itself`, `::test_a_blank_gateway_api_key_names_itself` |
| Odmowa jako odmowa / w trakcie uzupełniania | `test_gateway_history.py::test_a_401_from_the_gateway_is_a_refusal_not_an_empty_history` and `test_ingest.py::test_a_gateway_refusal_records_no_coverage` — the second asserts coverage stays `[]`, which is the load-bearing half |
| …/ przy zestawianiu strumienia | **No test.** Neither "nie raportuje się jako zdrowy" nor "nie ponawia w nieskończoność" is exercised |
| Poświadczenie do gatewaya nie trafia do logów | **No test.** The database side has one; the gateway side does not |
| **market-data-database-connection** | |
| Połączenie jest szyfrowane / konfiguracja nie wymusza | `test_config.py::test_a_database_url_that_does_not_require_tls_refuses_to_start`, `::test_a_database_url_that_requires_tls_is_accepted` |
| …/ serwer nie oferuje szyfrowania | **No test** — would need a server without TLS |
| Tożsamość, nie hasło | `test_db.py::test_credential_selects_a_service_principal_when_all_three_are_given`, `::test_credential_falls_back_to_default_when_none_are_given`, `::test_credential_rejects_a_partial_set`, plus `test_config.py::test_a_database_url_with_a_credential_refuses_to_start` |
| …/ poświadczenia nie da się uzyskać | `test_db.py::test_token_provider_wraps_a_credential_failure` — covers the error wrapping, not the refusal to start |
| Wygasające poświadczenie jest odnawiane / nowe połączenie | `test_db.py::test_token_provider_fetches_fresh_on_every_call`, with `::test_connect_with_a_user_passes_it_and_a_token_provider` and `::test_pool_with_a_user_passes_it_and_a_token_provider` proving the provider is wired into both paths |
| …/ odnowienie nie powiodło się | **No test** for "MUST NOT raportować się jako zdrowy" — market-data has no health-probe test at all |
| Poświadczenie nie wycieka do logów | `test_db.py::test_a_connection_failure_is_logged_without_the_credential`, `::test_connection_target_names_host_port_and_database_never_a_credential` |
| **market-data-api** | |
| Katalog osiągalny przez ten moduł / wyszukiwanie | `test_app.py:721` and `test_gateway_instruments.py::test_a_search_comes_back_unreshaped` — covered at both the HTTP route and the client |
| …/ klasy aktywów | `test_app.py:730`, `test_gateway_instruments.py::test_asset_classes_come_back_unreshaped` |
| Odmowa gatewaya jest przezroczysta | `test_gateway_instruments.py::test_a_401_is_a_refusal_not_an_empty_answer` (parametrised over all three calls), `::test_an_unreachable_gateway_is_named_as_such` |

## Deviations from design.md

- **The Static Web App deploy stores a secret**, against design.md's "no stored Azure secret" goal:
  `Azure/static-web-apps-deploy` accepts only a deployment token. The workflow says so in a comment
  rather than hiding it, which is the right handling — it is forced by Azure's tooling, not chosen.
- **`terraform apply` no longer runs in CI**, narrowing design.md's "Wdrożenia przez OIDC". The
  decision it rests on stands — the three application deploys still authenticate through OIDC with
  nothing stored — but infrastructure is now applied by the operator, because applying this root
  requires directory write and CI is not a privilege worth granting that to. Recorded in
  `terraform.yml`'s own header, not only here.
- **The bootstrap state was committed on the premise that it holds nothing sensitive.** The decision
  to keep bootstrap state local and readable is design.md's; the premise attached to it in
  `.gitignore` was wrong, and finding 1 was the consequence. `.gitignore`'s comment now says what is
  actually true — the state carries the account's keys, and `shared_access_key_enabled = false` is
  what keeps that survivable — instead of claiming there is nothing to worry about.

## Gaps

- **Nine spec scenarios have no test or only a partial one**, listed above. Three of them are the
  same shape and worth naming together: *"nie raportuje się jako zdrowy"* appears in two specs and
  market-data has no test that reads its health probe at all. The module's readiness reporting is
  asserted nowhere, which is exactly the signal App Service uses to decide on a restart.
- **Four tasks remain open in `tasks.md`**, each with a recorded reason: the subscription spending
  limit (3.5, a billing decision), the application role (4.7, folded into group 5), the first gateway
  deploy (7.4, blocked on merging to `main` by the OIDC subject filter), and end-to-end verification
  (11.4, which cannot run before 7.4).
  **Closed since — all four, as of 2026-08-09.** 3.5 is signed over to the operator (a spending
  decision, not a verification, and it has a September deadline). 4.7 is 5.7, done and checked
  against the live database. 7.4 deployed green after the GHCR image-name fix in PR #20. 11.4 was
  carried out in the follow-up change `authenticate-terminal-to-market-data`, which proves all three
  of its parts on the deployed platform.
- **No application has been deployed yet.** Findings 2-4 were all first-deploy failures, and they
  survived review-by-reading precisely because no deploy had been attempted; 11.4 is the task that
  would have caught them. The infrastructure side of that gap is now closed — the pipeline has run,
  and running it is what produced the four findings above, including the Key Vault one that reading
  the source three times did not. What remains unproven is the application deploy itself: no image
  has been built, pushed or started in App Service.
  **No longer true as of 2026-08-09** — both `capital-gateway` and `market-data` are built, pushed
  and running in App Service, and the terminal is live on Static Web Apps. This paragraph records
  where the review stood, not where the platform stands.
- **The reviewer's own reading missed the worst defect in the branch.** The Key Vault lockout was
  invisible in the source because it depends on *who runs Terraform*, and every run until that point
  had been the operator's. Worth remembering as a shape: a `data.azurerm_client_config.current` in a
  root that two different identities can apply is a latent identity swap, not a convenience.
- **Easy Auth on market-data is on with `Return401` while the terminal sends no token.** Documented
  in both the code and `tasks.md` as open work, so not a finding — but it means the deployed pair is
  non-functional until the browser-side 401 and CORS handling lands, and no task currently owns that.
