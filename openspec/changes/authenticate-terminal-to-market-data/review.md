## Verdict

The change does what it set out to do, and it is running. The terminal signs the operator in against
Entra and attaches the token in one place; `market-data` stays a plain token-protected API and hands
out a one-time ticket for the one path a browser cannot authenticate; and the whole chain was watched
working on the deployed platform rather than argued about — `POST /stream-tickets 200` followed by
`WebSocket /ws/candles?…&ticket=… [accepted]`, with a chart drawing candles at the other end.

The risk `design.md` flagged as the one that could force a different approach — Easy Auth answering
the CORS preflight with a `401` before the container sees it — **did not materialise**. App Service's
own CORS answers it, exactly as the design bet. The fallback was never needed.

What a later reader should not mistake for oversight: the terminal does **not** start sign-in by
itself. It shows "signed out" and a button. That is narrower than the spec scenario's "terminal
prowadzi go przez logowanie" reads, and it is recorded under Gaps rather than quietly redefined.

**Four defects were found by deploying this, none of them in the code this change set out to write.**
Three are fixed and one is not. They are listed under Findings because a change that surfaces them
owns saying so.

## Verified

Run locally at `5c8acd9`, the same commands and order as `.github/workflows/checks.yml`:

| Module | Command | Result |
|---|---|---|
| `capital-gateway` | `uv run ruff check .` | All checks passed |
| `capital-gateway` | `uv run pytest -q` | 154 passed, 8 skipped |
| `market-data` | `uv run ruff check .` | All checks passed |
| `market-data` | `uv run pytest -q` | 510 passed, 7 skipped, 28.07 s |
| `terminal` | `pnpm contract:check` | Contract is up to date |
| `terminal` | `pnpm lint` / `pnpm typecheck` | clean |
| `terminal` | `pnpm test` | 242 passed, 18 files |
| `infra` | `terraform fmt -check` / `validate` | clean / Success |

`capital-gateway` is green here, unlike the previous change's review — finding 5 of
`provision-azure-platform` fixed the `.env`-sensitive test.

### Verified on the deployed platform

Not a description of a screen. Every row is a log line, a database row, or an HTTP response:

| Claim | Evidence |
|---|---|
| Terraform applied | `4 added, 2 changed, 0 destroyed`, from a saved plan so what applied is what was reviewed |
| CORS preflight passes Easy Auth | `OPTIONS /health` → `200`, `Access-Control-Allow-Origin`, `Access-Control-Allow-Headers: authorization` |
| The stream left Easy Auth's cover | `"WebSocket /ws/candles?…" 403` + `connection rejected` — the module's refusal, not the platform's `401` |
| …and is still guarded | that `403` is `websocket.close(1008)` before `accept()`, i.e. the ticket check |
| Sign-in works, without a consent screen | pre-authorization holds; the operator reached the app with an existing session |
| Token reaches every route | `GET /instruments?asset_class=INDICES 200`, `GET /asset-classes 200`, `POST /pairs 201`, `GET /jobs 200` |
| The stream opens on a ticket | `POST /stream-tickets 200` → `WebSocket …&ticket=UCUW… [accepted]` |
| Ingest writes to the Azure database | 19 880 candles in `market_data`, with coverage recorded |
| A dropped stream returns by itself | connection broken by an app restart; the chart came back, which a spent ticket could not have done |
| No operator token in any URL | the access log carries the ticket and nothing else |
| A refusal is logged with its reason and no ticket value | `stream handshake refused: no valid ticket`, in Application Insights |

## Spec coverage

| Requirement / Scenario | Proven by |
|---|---|
| **market-data-browser-access** | |
| Strumień zestawia się poświadczeniem jednorazowym / konsument prosi | `test_app.py::test_a_ticket_is_issued_with_the_time_it_stays_good_for` |
| …/ to samo poświadczenie użyte dwa razy | `test_tickets.py::test_a_ticket_is_spent_only_once` and `test_app.py::test_a_ticket_works_once_and_the_first_connection_survives_the_second_try` — the second also asserts the first connection is undisturbed |
| …/ poświadczenie przeleżało | `test_tickets.py::test_a_ticket_expires_even_if_it_is_never_spent`, `::test_a_ticket_is_still_good_a_moment_before_it_expires`, `test_app.py::test_a_handshake_with_an_expired_ticket_is_refused` |
| …/ nieodgadywalność | `test_tickets.py::test_two_tickets_are_never_the_same_ticket` — 100 distinct values, each ≥ 40 characters |
| Bez ważnego poświadczenia strumień się nie zestawia / bez biletu | `test_app.py::test_a_handshake_without_a_ticket_is_refused` — asserts refusal **before** `accept()` |
| …/ bilet nieznany | `::test_a_handshake_with_a_ticket_the_archive_never_issued_is_refused`. "Nie rozróżnia nieistniejącego od wygasłego" is proven by construction — one message covers all four cases — rather than by comparing two responses |
| …/ dwie różne przyczyny odmowy | `::test_the_two_reasons_a_handshake_is_refused_are_told_apart` |
| Poświadczenie wydaje się wyłącznie uwierzytelnionemu / bez tożsamości | `::test_a_ticket_is_refused_when_the_platform_identified_nobody` — asserts `401` **and** that no ticket was created |
| …/ konfiguracja lokalna | `::test_a_ticket_is_issued_without_a_principal_when_nothing_stands_in_front`, plus every other handshake test, which all carry a ticket |
| …/ bilet zapamiętuje, komu wydany | `::test_a_ticket_records_the_principal_the_platform_identified` |
| Wywołanie z przeglądarki przychodzi z uznanego adresu | **No automated test.** CORS lives on App Service (`infra/app-service.tf`), so there is nothing in the module to assert. Verified live — see the deployment table. A guard exists against the likelier regression: `market_data/app.py` and `infra/app-service.tf` both carry the "do not add CORSMiddleware" note, since two layers would double the header |
| Poświadczenia nie trafiają do logów / odmowa w logu | `::test_no_ticket_value_reaches_the_logs` — asserts the issued value is absent and the reason present, over both an accepted and a refused handshake |
| …/ wydane poświadczenie w logu | same test — `stream ticket issued to operator-object-id` is present, the value is not |
| **terminal-identity** | |
| Operator loguje się kontem organizacji | **Partial.** `entra.ts` has no test by design — it is the one file that knows Entra exists, and the seam that makes everything else testable is `Identity`. Verified live instead. Silent renewal and the redirect round trip are not asserted anywhere |
| …/ stan zalogowania widoczny w powłoce | **No test.** `App.test.tsx` mocks the identity as `unconfigured`, which is the branch that renders nothing |
| Każde wywołanie archiwum niesie poświadczenie | `http.test.ts::carries the token on every request, whatever the route` — including a route that exists only in the test, standing in for one written later |
| …/ katalog instrumentów | same test's second route, plus `GET /instruments 200` on the deployed platform |
| Odmowa z powodu tożsamości odróżniona od awarii źródła / naprawiona odnowieniem | `http.test.ts::renews the token once and retries` — asserts both requests' headers, so the retry provably carries the *new* token |
| …/ odnowienie nie naprawia | `::gives up after one renewal rather than looping` — asserts exactly two requests and one renewal |
| …/ nie jako niedostępność | `::says the operator is signed out rather than that the archive is unreachable` |
| Połączenie strumieniowe zestawiane poświadczeniem jednorazowym | `archive.test.ts::asks for a ticket and puts it in the address, never the token` — asserts the token is in the header and absent from the URL |
| …/ świeży bilet na każdą próbę | `::asks for a new ticket on every attempt` — drives a real drop and asserts two different tickets |
| Poświadczenie nie jest pokazywane ani utrwalane | `http.test.ts::never quotes the credential back in a message`. The `sessionStorage` choice is not asserted |
| Brak konfiguracji oznacza pracę bez niej | `config.test.ts::resolveEntra` (three cases: complete, absent, partial) and `http.test.ts::sends no credential at all when none is configured` |
| **terminal-market-data** (modified) | |
| Utrata tożsamości zatrzymuje ponawianie | `socketHub.test.ts::stops trying and says to sign in, rather than reporting a dead source` — asserts no socket is ever opened |
| Inna przyczyna nadal znaczy „ponawiaj" | `::keeps retrying when the address could not be got for any other reason` |
| Rozstrzygnięcie odmówione z powodu tożsamości | `::stops when the diagnosis is itself refused for want of an identity` — asserts no second address is even asked for |
| Każda próba poprzedzona pobraniem biletu | `archive.test.ts::asks for a new ticket on every attempt`; the hub's own tests assert the ordering |
| Pozostałe scenariusze wymagania | unchanged and still covered by the pre-existing `socketHub.test.ts` cases, which were rewritten only to await the now-asynchronous connect |

## Findings

| # | What | Status |
|---|---|---|
| 1 | **Static Web Apps had no `navigationFallback`**, so every address except `/` answered its 404 page — since the terminal was first deployed. Invisible because clicking between tabs never asks a server anything, and untestable in a suite that drives the router in memory. Sign-in surfaced it: MSAL returns the operator to the address they started from, as a full navigation, and that address is a tab | **Fixed**, PR #23, with a test holding the fallback against the tab list |
| 2 | **`migrations/env.py` called `fileConfig` with alembic's default `disable_existing_loggers=True`**, switching off every `market_data.*` logger for the whole test session. Any test asserting on what is or is not logged would have passed for the wrong reason | **Fixed** in this change |
| 3 | **Nothing gave the root logger a level or a handler.** Uvicorn configures only its own three, so the deployed container printed access lines and nothing this module wrote; Application Insights was gated by the same default `WARNING`. A collection job that never started looked exactly like one running quietly | **Fixed**, PR #24 |
| 4 | **The Application Insights exporter logged about itself**, once the root logger had a level: it logs each telemetry upload, and that line is telemetry, so it is uploaded and logged again. 965 entries in six minutes from a process with almost no traffic | **Fixed**, PR #25 |
| 5 | **A collection job sat at eight pending chunks** across a restart and a retry, with the worker loop polling every five seconds. Permissions ruled out (the app role has `UPDATE` on every table), row locks ruled out (none), and the claim query run by hand against the same data returned a chunk and marked it running. After the two logging deploys it worked immediately — 35 096 candles in 52 provider requests — and has worked since | **Unresolved.** Cause never identified. Now *observable*: a worker that stops for any reason but `stop()` logs it with the traceback (`_report_worker_death`, with tests) |
| 6 | **The per-pair Retry button retries the whole job.** It calls `retryJob(jobId)`, so clicking it on one resolution moves every row to running. The placement promises something narrower than the action | **Unresolved**, reported by the operator during verification |
| 7 | **`terraform.yml`'s header claimed CI's plan 403s on every `azuread_application`.** It does not, and has not since `var.operator_object_id` was fixed — the plan on this change's PR came back clean and matched the local one resource for resource | **Fixed** in this change: corrected rather than deleted, because "CI cannot read the directory" is the kind of belief that rules out ideas it should not |
| 8 | **`test_the_runner_claims_and_settles_a_pending_chunk` is flaky** — it waits `asyncio.sleep(0.1)` for a worker to finish a chunk. Failed once in a full run, passed alone and on re-run | **Unresolved**, worth tightening separately |

Findings 5 and 6 belong to `market-data`'s collection jobs, not to this change, and are recorded in
`tasks.md` as found-out-of-scope. They are the natural content of the next change, together with 8.

## Deviations from design.md

- **Task 2.1 landed in `app-service.tf`, not `entra.tf`.** That is where the `market-data`
  registration already lived; moving it would have been diff noise for no gain.
- **One redirect URI, not two.** The design assumed both `https://host` and `https://host/` could be
  registered against MSAL's default. The provider refuses a redirect URI without a trailing slash
  when there is no path segment, so the terminal sets `redirectUri` explicitly instead. Caught by
  `terraform plan`, before anything was applied.
- **`navigationFallback` was not in the design at all.** It had to be, and nobody knew — see
  finding 1.

## Gaps

- **CORS has no automated test**, because it is not in the module. The comment in two places is the
  guard against the regression that would actually happen; the requirement itself rests on the live
  check recorded above.
- **The shell's sign-in indicator is untested.** `App.test.tsx` mocks identity as `unconfigured`,
  which renders nothing, so the two states an operator actually sees are asserted nowhere.
- **`entra.ts` is untested**, deliberately: it is the seam's far side. The cost is that silent token
  renewal and the redirect round trip — the parts most likely to break on an MSAL upgrade — are
  covered only by having watched them work once.
- **Sign-in is offered, not started.** The spec scenario reads as the terminal leading the operator
  through it. A button is the weaker reading, and the operator's first attempt did stall on it
  (compounded by finding 1). Worth closing either by starting sign-in when identity is configured and
  there is no session, or by narrowing the scenario to what the terminal does.
- **The ticket store is a dict in one process.** Stated in the design, in the module's README and in
  a comment at the store. It is a correct choice today and a silent failure the moment
  `worker_count` changes — a stream that refuses now and then, pointing nowhere near the cause.
