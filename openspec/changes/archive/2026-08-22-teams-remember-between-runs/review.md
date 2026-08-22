## Verdict

A team now keeps notes between runs: one table beside the revision, two tools served by
this process itself, and per-agent permission expressed with the mechanism that already
existed — the tool names a definition assigns. Nothing was added to `AgentDefinition`, so
no saved revision had to be rewritten, and no setting was added, so no `.env` had to change.

Two things a later reader should not mistake for oversights. First, **`announced_snapshot`
no longer returns `None`** and `check_definition`'s `announced` parameter is no longer
optional: with a source this process always serves, "nothing is configured" stopped being a
state a snapshot could be in, and the narrower claim it used to make travels as
`unconfigured`. Second, **the assignment is now enforced at call time**, which is a change
in behaviour for every tool, not only the memory ones — a model that names a tool it was not
given is refused rather than dispatched. That was deliberate: being handed a narrower list
protects against a mistake, never against an attempt, and it only became load-bearing once
one agent may write what another may only read.

Knowingly not done: memory is not in the conversation's tool set (`teams_tools/`) — that is
a separate decision with its own cost against `SURFACE_CEILING_CHARS`. No TTL, no search, no
per-author read filtering; the ceilings and the operator's hand are the whole policy for v1.

## Verified

Run from `modules/workbench` and `modules/terminal` at `ef24382` plus the coverage tests
added while writing this review. The suite is split because running every container at once
was killed for memory (exit 137) on this machine — the split is a local constraint, not a
skipped job; CI runs them together.

| Command | Result |
|---|---|
| `uv run pytest tests/teams -q` | 406 passed |
| `uv run pytest tests/agent tests/teams_tools tests/test_*.py -q` | 451 passed |
| `uv run ruff check .` | All checks passed |
| `uv run pyright` | 0 errors, 0 warnings |
| `npx vitest run` (terminal) | 673 passed, 51 files |
| `npx eslint .` · `npx tsc -b --noEmit` | clean |
| `node scripts/contract.mjs check` | Every contract is up to date |
| `openspec validate teams-remember-between-runs --strict` | valid |

## Findings

| Severity | Where | Finding | Status |
|---|---|---|---|
| High | `teams/tools/assignment.py:257` | The refusal naming an unconfigured server fired whenever *any* server lacked an address, so a team assigned a market tool with market-mcp answering and trading-mcp unset was told to go set a variable instead of being told the tool is not announced. Caught by `test_a_tool_the_server_stopped_announcing_refuses_the_run`. | FIXED in `3dd6c2e` — the branch now requires `not registry.remote()` |
| Medium | `teams/tools/client.py:436` | `registry.configured()` became "every source", which two refusals were reading as "is any tool server there" — with memory always configured, "no tool server is configured" could never fire again. | FIXED in `3dd6c2e` — `remote()` added and both call sites moved to it |
| Medium | `teams/store/memory.py:57` | An owner check read before the insert would be stale by the time the insert lands, since a run holds no lock on its team. | FIXED in `faddf1c` — the check rides inside `INSERT ... SELECT` |
| Low | `teams/routers/schedules.py:278` | A trigger could name `memory_read`, whose condition can never come true: the clock calls it with no run bound, so it answers unavailable forever. | FIXED in `3dd6c2e` — local names subtracted before the trigger check |
| Low | `teams/store/memory.py:31` | Two entries written in one transaction can share `created_at` to the microsecond, so a read ordered only by time would drop a different entry at the ceiling depending on the plan. | FIXED in `faddf1c` — `id DESC` behind `created_at DESC`, in the statement and the index |

Not a finding, but worth recording as a decision: `run_id` is `ON DELETE SET NULL` rather
than `CASCADE`. An entry that outlives its run is still true, and the provenance is
legibility rather than the thing being stored.

## Spec coverage

Test paths are relative to `modules/workbench` unless marked `terminal:`.

| Requirement / Scenario | Proven by |
|---|---|
| **teams-memory — Pamięć należy do zespołu i przeżywa przebieg** | |
| Kolejny przebieg czyta to, co zostawił poprzedni | `tests/teams/test_memory_tools.py::test_what_one_run_writes_the_next_run_reads` |
| Wpis zostaje po przebiegu, który się nie udał | `tests/teams/test_memory_tools.py::test_a_note_survives_the_run_that_failed_after_writing_it` |
| Nowa rewizja nie zabiera pamięci | `tests/teams/test_memory_tools.py::test_a_newer_revision_reads_what_an_older_one_remembered` |
| Pamięć nie sięga poza zespół | `tests/teams/test_store_memory.py::test_memory_does_not_reach_across_teams` |
| **teams-memory — Wpis raz zapisany się nie zmienia** | |
| Agent sprostowuje wcześniejszą notatkę | `tests/teams/test_memory_tools.py::test_a_correction_is_another_note_and_the_first_one_stays` |
| **teams-memory — Wpis powstaje decyzją agenta i zostaje w śladzie przebiegu** | |
| Przebieg bez wywołania narzędzia pamięci | `tests/teams/test_memory_tools.py::test_a_run_that_never_calls_the_tool_leaves_no_note` |
| Ślad pokazuje, co zespół przeczytał i co zostawił | `tests/teams/test_memory_tools.py::test_a_read_and_a_write_both_land_in_the_runs_trace` |
| **teams-memory — Odczyt oddaje najnowsze wpisy, a nie całą pamięć** | |
| Pamięć większa niż sufit odczytu | `tests/teams/test_memory_tools.py::test_the_read_says_when_it_did_not_hand_over_everything`; `tests/teams/test_store_memory.py::test_the_read_says_there_is_more_than_it_handed_over` |
| Zespół bez ani jednego wpisu | `tests/teams/test_memory_tools.py::test_a_team_that_has_written_nothing_reads_an_empty_memory` |
| **teams-memory — Pamięć ma granice zapisane w module, nie w konfiguracji** | |
| Wpis dłuższy niż wolno | `tests/teams/test_memory_tools.py::test_a_note_over_the_length_ceiling_is_refused_and_the_run_carries_on`; on disk `tests/teams/test_store_memory.py::test_an_entry_too_long_is_refused_by_the_database` |
| Agenci wyczerpali pulę zapisów przebiegu | `tests/teams/test_memory_tools.py::test_a_run_stops_being_allowed_to_write_after_its_ceiling` |
| **teams-memory — Pamięć jest widoczna dla operatora i usuwana wyłącznie przez niego** | |
| Operator usuwa nietrafiony wpis | `tests/teams/test_memory_routes.py::test_the_operator_deletes_one_entry`; no writing route: `::test_there_is_no_route_that_writes_a_memory_entry` |
| Pamięć cudzego zespołu | `tests/teams/test_memory_routes.py::test_somebody_elses_memory_reads_like_a_team_that_is_not_there`; `::test_a_stranger_cannot_delete_an_entry` |
| **teams-memory — Wycofanie zespołu z katalogu nie zabiera jego pamięci** | |
| Wycofanie zespołu mającego pamięć | `tests/teams/test_store_memory.py::test_retiring_a_team_leaves_its_memory_readable` |
| **teams-runs — Przebieg niesie zespół i właściciela** | |
| Uruchomienie z terminala | `tests/teams/test_memory_tools.py::test_the_entry_carries_the_agent_that_wrote_it` (through `execute_run`) — see Gaps for the route's own leg |
| Uruchomienie z harmonogramu | `tests/teams/test_scheduler_clock.py::test_what_a_scheduled_run_remembers_belongs_to_the_schedules_owner` |
| **teams-tool-access — Narzędzie w tym samym procesie jest źródłem, ale nie serwerem** | |
| Zespół sięgający wyłącznie po narzędzia z procesu | `tests/teams/test_memory_tools.py::test_a_team_reaching_only_for_memory_plans_with_no_server_configured` |
| Nazwa z procesu zderza się z nazwą z serwera | `tests/teams/test_memory_tools.py::test_a_server_announcing_a_memory_name_refuses_the_run` |
| Zapis rewizji z narzędziem z procesu | `tests/teams/test_memory_routes.py::test_a_revision_may_assign_a_tool_this_process_serves_itself` |
| **teams-tool-access — Agent dostaje narzędzia wskazane w definicji, a nie wszystkie** | |
| Rola z zawężonym zestawem | `tests/teams/test_tool_assignment.py::test_an_agent_gets_the_tools_the_definition_named_and_no_others` |
| Narzędzie znika po stronie serwera | `tests/teams/test_tool_assignment.py::test_a_tool_the_server_stopped_announcing_refuses_the_run` |
| Model woła nazwę, której nie dostał | `tests/teams/test_memory_tools.py::test_an_agent_that_may_only_read_cannot_write`; `::test_the_refusal_names_what_the_agent_does_have` |
| Model woła nazwę, której nikt nie ogłasza | `tests/teams/test_memory_tools.py::test_a_name_the_model_invented_is_answered_not_dispatched` |
| **teams-tool-access — Moduł nie trzyma kopii tego, co ogłasza serwer** | |
| Opis narzędzia zmienia się po stronie serwera | `tests/teams/test_tool_assignment.py::test_descriptors_come_from_the_session_not_from_the_revision` |
| Rewizja z narzędziem modułu | `tests/teams/test_memory_routes.py::test_a_revision_may_assign_a_tool_this_process_serves_itself` |
| **terminal-teams — Pamięć zespołu jest widoczna przy zespole** | |
| Operator ogląda pamięć zespołu | `terminal: src/teams/MemoryPanel.test.tsx::lists the notes with the agent that wrote each one` |
| Operator usuwa nietrafiony wpis | `terminal: src/teams/MemoryPanel.test.tsx::asks first, then removes the one the operator picked`; refusal: `::keeps the refusal beside the question it explains` |
| Zespół, który jeszcze nic nie zapamiętał | `terminal: src/teams/MemoryPanel.test.tsx::says a team has remembered nothing rather than showing an empty box` |

## Gaps

**"Uruchomienie z terminala" is proven one call short of the route.** Every memory test
drives `execute_run` directly, and the clock's leg of `start_run_on_revision` has its own
test; what has no test of its own is `POST /teams/{team_id}/runs` reaching that same
function with `revision["team_id"]`. Closing it properly needs a model provider swapped into
a running app, which this suite has no seam for — the route builds the real one from
`app.state`. The two callers share one function and one line each, and the clock's test
covers that function, so the untested surface is the route's own argument. Recorded rather
than hidden; a seam for injecting the provider into `TestClient` would close it and is worth
having for more than this.
