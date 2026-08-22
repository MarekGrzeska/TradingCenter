# Review — a-strategy-is-a-catalogue-entry

## Verdict

The module ships whole: a catalogue with one entry, a runtime that decides on closed bars
and records why it did not, two surfaces with a record of who may reach which, and a
backtest that calls the loop's own `evaluate`. Twenty-one of twenty-four tasks are done;
the three left are operator work that needs a running stack or an Azure apply, and each is
marked in `tasks.md` with the reason rather than quietly dropped.

Two things a later reader should not mistake for oversights. **The skeleton was copied from
market-data and workbench, not from polymarket-data** as the artifacts say — that module is
not on `main`, and taking a dependency on an unmerged branch was the wrong trade;
`design.md` records the correction. And **the daily loss budget lives in the backtest and
not among the platform's live gates**, though the proposal listed it with the shared ones:
a daily budget counts realised results, and the live module records decisions rather than
outcomes, so there is nothing there to count. That is a finding from building it, not a
scope cut.

## Verified

Run in `modules/strategy` at 05e3243:

```
uv run pytest -q     → 194 passed, 1 warning
uv run pytest -m db  → 58 passed, 136 deselected     (throwaway PostgreSQL, testcontainers)
uv run ruff check .  → All checks passed!
uv run pyright       → 0 errors, 0 warnings, 0 informations
```

In `scripts`: `uv run pytest -q` → 111 passed, 21 skipped — the repository's own consistency
tests (service table, guide, deploy workflows) after this change wired the module in.

In `infra`: `terraform fmt -check -recursive` clean, `terraform init -backend=false` +
`terraform validate` → "Success! The configuration is valid." Locally there was no plan and
no apply — that is the operator's, and `terraform-apply.yml` refuses a plan touching
`azuread_*` anyway, which this one does through the Easy Auth module.

CI's own `plan` job did run against real state, and it is what turned up the first finding
below. Reading it is not optional before an apply.

Not run: the stack itself. The dev database container and the fixed ports are shared across
worktrees and another agent was working in the main one, so nothing here was exercised
against a live market-data, workbench or Postgres beyond the throwaway container.

## Findings

| Severity | Where | Finding | Status |
|---|---|---|---|
| **high** | Terraform state, not this diff | The plan on PR #201 reads `6 to add, 4 to change, **38 to destroy**`, and all 38 destroys are `polymarket-data`'s production footprint: 32 firewall rules, its App Service, the `polymarket` database, three Easy Auth resources and a Key Vault policy. That module was applied to production from a branch that is not on `main`, so it lives in state and not in the code any plan from `main` reads. **Applying this branch as it stands would delete a running module and its database.** Nothing in this change caused it — this is simply the first PR to touch `infra/` since that apply, so it is the first plan to say so. Before any apply: merge `polymarket-data-joins-the-stack` and rebase, or apply from a branch holding both. | open — blocks the apply, recorded in `design.md`'s Migration Plan and on the PR |
| medium | `strategy/caller_access.py:REST_PATHS` | The record named `/backtests` and `/backtests/{run_id}` before any route published them. A record naming routes that do not exist grants nothing and hides what it does grant. Found by writing the reverse test (`test_the_record_names_no_route_that_is_gone`), which is the half of that pair usually left out. | FIXED — 50e8e14 removed them, 8cffc96 restored them with the routes |
| medium | `tests/test_caller_access.py` | The first version of the record-versus-document test walked `app.router.routes`; newer FastAPI wraps an included router in a `_IncludedRouter` with no `path`, so it saw four framework routes and none of this module's — a check that passed by looking at nothing. | FIXED — 50e8e14 reads `app.openapi()` instead |
| low | `tests/test_layering.py` | The entry rules were applied to `catalogue/__init__.py` too, which imports every entry and is *supposed* to — it is the one file a new strategy changes. | FIXED — c08ea01 excludes the registry by name |
| low | `strategy/store.py:add_parameter_set` | The store writes whatever mapping it is handed; only the two routes resolve defaults first. A caller writing an unresolved set would make "what was this decided with" answer `{}`, and that answer would drift if an image changed a default. Both writers today resolve, and enforcing it in the store would put the catalogue inside it — a layering trade not worth making for a path that does not exist. Written down rather than fixed. | open, documented |
| low | `strategy/archive.py:_indicators` | Fact-to-result mapping relies on the archive answering in request order. Checked rather than trusted — a mismatched `id` raises instead of handing a strategy one indicator's numbers under another's name. | by design, tested |

No findings survived verification in the backtest arithmetic, the gates, or the migration
chain.

## Spec coverage

Tests live in `modules/strategy/tests/`.

### strategy-catalogue

| Requirement / Scenario | Proven by |
|---|---|
| Strategia jest wpisem katalogu — Druga strategia wchodzi do katalogu | `test_layering.py::test_the_runtime_never_names_a_strategy`, `::test_an_entry_knows_only_the_contract` |
| — Parametr poza zadeklarowanym zakresem | `test_spec.py::TestParameters::test_a_value_outside_its_range_is_refused`, `test_api.py::TestParameterSets::test_a_value_out_of_range_is_refused_now_rather_than_at_the_next_bar` |
| Ocena jest czystą funkcją — Dwa wywołania na tych samych wejściach | `test_baseline.py::TestItIsAFunction::test_the_same_readings_decide_the_same_way` |
| — Wpis sięga poza argumenty | `test_layering.py::test_an_entry_does_no_io`, `::test_an_entry_does_not_read_a_clock` |
| Decyzja niesie powód i pochodzenie — Setup odrzucony przez bramkę strategii | `test_spec.py::TestDecision::test_a_refusal_must_carry_a_reason`, `test_baseline.py::TestWhatItRefusesToGuess` (5 tests) |
| — Decyzja wraca do swojego zestawu parametrów | `test_api.py::TestDecisions::test_a_decision_names_the_parameter_version_it_was_decided_under` |
| Pierwszym wpisem jest strategia odniesienia — Katalog przed pierwszą strategią właściwą | `test_catalogue.py::test_the_catalogue_carries_the_strategy_of_reference`, `::test_every_entry_resolves_its_own_defaults` — **partial**, see Gaps |

### strategy-runtime

| Requirement / Scenario | Proven by |
|---|---|
| Ocena zapada wyłącznie na domkniętej świecy — Fakty dla świecy formującej się | `test_archive.py::TestTheLastClosedBar::test_it_is_read_from_the_closed_candles_route` |
| Fakty pochodzą z archiwum, jedną drogą — Wpis nazywa wskaźnik spoza katalogu | `test_catalogue.py::TestFactsAreAnnounced::test_an_indicator_the_archive_does_not_announce_is_refused_by_name`, `test_api.py::TestWatches::test_a_strategy_whose_facts_the_archive_does_not_announce_is_refused` |
| Dziura w danych nie jest odpowiedzią — Zakres z niedopokrytym oknem | `test_loop.py::TestWhenItCannotSee::test_a_gap_in_the_range_refuses_the_setup`, `test_gates.py::TestCoverage` (3 tests), `test_store.py::TestDecisions::test_a_refusal_for_want_of_data_reads_apart_from_the_strategys_own` |
| Platforma nie ma drogi do konta — Strategia produkuje sygnał wejścia | `test_layering.py::test_nothing_in_this_module_can_reach_an_account`, `test_loop.py::TestOnePass::test_a_setup_is_recorded_with_its_levels` |
| Każda ocena zostaje zapisana i daje się odtworzyć — Odtworzenie zapisanej oceny | `test_store.py::TestReplay::test_a_recorded_decision_decides_the_same_way_again` |
| Platforma bez strategii — Start bez aktywnych strategii | `test_loop.py::TestEveryWatch::test_no_watches_at_all_is_a_supported_state`, `test_api.py::TestAPlatformWatchingNothing::test_the_surfaces_answer_empty_rather_than_failing` |
| — Dezaktywacja jednej z wielu strategii | `test_store.py::TestWatches::test_deactivating_one_leaves_the_others_running`, `test_api.py::TestWatches::test_deactivating_a_watch_leaves_the_others_running`, `test_loop.py::TestEveryWatch::test_a_deactivated_watch_is_not_evaluated` |

### strategy-tools

| Requirement / Scenario | Proven by |
|---|---|
| Zestaw narzędzi wyłącznie czyta — Lista narzędzi nie zawiera zapisu | `test_tools_surface.py::TestTheSurfaceOnlyReads::test_there_is_no_tool_that_changes_anything`, `::test_every_announced_tool_says_so_structurally` |
| pending_setups jako warunek wyzwalacza — Wyzwalacz budzi się na kandydacie | `test_tools_surface.py::TestPendingSetups::test_the_count_is_the_field_a_trigger_watches`, `::test_the_number_is_the_one_the_woken_team_will_read` |
| — Strategia bez oczekujących setupów | `test_tools_surface.py::TestPendingSetups::test_a_strategy_standing_on_nothing_answers_zero_not_an_error` |
| Powierzchnia zna tożsamość wołającego — Wołający spoza listy | `test_caller_access.py::TestWhoGetsIn::test_the_rest_caller_does_not_reach_the_tools`, `::test_a_request_with_no_identity_is_refused` |

### strategy-backtest

| Requirement / Scenario | Proven by |
|---|---|
| Backtest woła tę samą funkcję — Przebieg przyrostowy i wsadowy | `test_backtest.py::TestLookAhead::test_incremental_and_batch_agree` |
| Przedłużenie historii nie zmienia decyzji — Ten sam początek, dłuższy koniec | `test_backtest.py::TestLookAhead::test_a_longer_range_does_not_change_the_common_part`, `TestSlicing` (3 tests) |
| Wynik nazywa koszty i parametry — Raport z przebiegu | `test_backtest.py::TestTheReport::test_a_run_names_its_costs_its_parameters_and_its_range`, `::test_the_same_run_twice_gives_the_same_report` |
| Porównanie na tych samych danych — Zestawienie dwóch strategii | `test_backtest.py::TestComparing::test_runs_on_the_same_data_and_costs_compare` |
| — Zestawienie przebiegów o różnych składnikach | `test_backtest.py::TestComparing::test_runs_on_different_ranges_are_refused`, `::test_runs_on_different_costs_are_refused` |
| Backtest niczego nie zmienia — Przebieg a reszta systemu | `test_backtest_runs.py::TestARunChangesNothingElse::test_a_backtest_leaves_the_live_record_alone` |

### strategy-database-connection

| Requirement / Scenario | Proven by |
|---|---|
| Tożsamość albo pętla zwrotna — Host zdalny bez tożsamości | `test_config.py::TestTheDatabaseRule::test_local_mode_refuses_a_remote_host` |
| — Poświadczenie w adresie obok tożsamości | `test_config.py::TestTheDatabaseRule::test_identity_mode_refuses_a_credential_in_the_url` |
| — Host zdalny bez wymuszonego szyfrowania | `test_config.py::TestTheDatabaseRule::test_identity_mode_refuses_a_url_without_tls` |
| Własna baza — Migracje platformy | `test_runtime.py::test_the_migrations_are_beside_the_package`, `test_migrate.py::test_the_chain_reaches_head_and_the_check_agrees` — **partial**, see Gaps |
| Moduł sam migruje pod blokadą — Wdrożenie niosące nową rewizję | `test_migrate.py::test_the_chain_reaches_head_and_the_check_agrees` |
| — Baza wyprzedza obraz | `packages/tc-runtime/tests/test_schema_version.py` — the shared package, tested once there (rule 5 of "How much test is enough") |
| — Nowa tabela jest od razu użyteczna | **gap**, see below |

## Gaps

Three scenarios are not proven by a test in this module, and each is listed rather than
argued away:

- **"Katalog przed pierwszą strategią właściwą"** is proven for the catalogue's shape but
  not for the claim that the baseline's facts name indicators the *real* archive announces.
  `test_catalogue.py` checks against a hand-written set. Proving it needs a running
  market-data, so it is covered instead at registration time — `POST /watches` refuses a
  strategy whose facts the archive does not announce, by name.
- **"Migracje platformy dotyczą wyłącznie własnej bazy"** holds structurally — the module
  has one alembic chain against one database URL — but nothing asserts it against a server
  holding two databases. The `db` fixture is a throwaway container with one.
- **"Nowa tabela jest od razu użyteczna"** is about the production role owning its schema.
  The `db` tests run as the container's superuser, so they cannot observe it. This is what
  `scripts/grant-schema-ownership.sql` is for, and it is the one manual step per database
  this repository has always kept — recorded in the README, in `database.tf` and in the new
  Terraform output.

Deferred, and operator work rather than gaps in the code:

- **4.4** — the end-to-end trial of the seam (a workbench trigger on `pending_setups`
  starting a team). Needs the whole stack. The seam's shape is covered by
  `test_tools_surface.py::TestPendingSetups::test_the_number_is_the_one_the_woken_team_will_read`.
- **5.5** — the backfill of the target instruments through market-data's jobs, and the
  `coverage` check afterwards. The backtest is finished and waiting on data.
- **6.3** — the production apply, in the order `design.md`'s Migration Plan states: settings
  and identities before the image that enforces them. `terraform apply` is never CI's, and
  this plan touches `azuread_*`, which `terraform-apply.yml` refuses by design.
