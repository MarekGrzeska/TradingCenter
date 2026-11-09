## Verdict

Wdrożone (PR #416, merge `666708cb`, `deploy-vps` 42682572900 zielony): kroki obok agentów w rewizji zespołu, katalog
przepisów z `strategy_execute`, jedna próba na świecę sygnałową (`trades.attempt_key`), powiadomienie zapasowe agenta,
granica dobowa trzymająca agentów, a nie kroki, kroki w `tc-team-tools` i na obrazie terminala.

Świadomie niedokończone: próba 8.3 trwa. Zamiast zespołu na innym koncie demo operator wybrał następcę teamu 8 na **tym
samym** koncie demo2 (`325778595166630174`) — team 12, założony z Claude Code, nie z Telegrama, rewizja 23
(`wait_for_bar_seconds` 60, `max_bar_age_seconds` 300), harmonogramy 09:35, 09:38, 14:00 i 14:10 America/New_York;
harmonogramy teamu 8 wyłącza operator. Porównanie tygodnia z teamem 8 nie powstanie w tej formie, bo oba nie mogą
handlować na jednym koncie naraz.

## Verified

- `modules/workbench`: `uv run pytest` z `-m db` (Docker) → 3434 passed, 11 skipped; `ruff check .` czysto, `pyright` 0 błędów.
- `modules/terminal`: testy `src/teams` 110 passed; `lint`, `typecheck` czysto; `contract:check` aktualny.
- `openspec validate team-deterministic-steps --strict` → valid.
- CI PR #416: `changes`, `openspec`, `terminal`, `workbench` zielone; `checks` na `main` 42681054025 zielony.
- Produkcja: `create_team` z `steps` i `trading.account_id` przez `tc-team-tools` zapisał team 12; `read_team` zwraca krok
  z parametrami; terminal po odświeżeniu rysuje krok jako osobny blok.
- 8.2: `id` z `place_order` równe id pozycji w `get_positions` na koncie realnym, przebieg 338.

## Findings

Przegląd kodu gałęzi przed scaleniem dał 14 uwag; wszystkie poprawione w `34b65048`. Najważniejsze:

| Severity | Where | Finding | Status |
|---|---|---|---|
| High | `runner/engine.py` | Agent padający obok kroku (błąd modelu, granica kosztu, granica zleceń) podnosił wyjątek, a LangGraph anuluje wtedy węzły rodzeństwa — także krok w trakcie zlecenia. | FIXED: `_Run.stop_node` zbiera porażkę, przebieg kończy się `failed` z pierwszą przyczyną; `test_step_fallback.py` |
| High | `steps/strategy_execute.py::decide` | Drugi przebieg w tej samej świecy po wejściu widział `enter` i własną pozycję — silnik nie ma jeszcze pozycji (wypełnia na otwarciu następnej świecy), więc przepis zamknąłby świeżo otwartą pozycję. | FIXED: `skipped` „wejście na tej świecy już wykonane”; tabela w `test_strategy_execute.py` |
| High | `strategy_execute.py::_enter` | Odpowiedź `unsettled` (PENDING) albo bez `id` liczona jako wejście. | FIXED: tylko `outcome == settled` z `id`, reszta `unknown` |
| Medium | `strategy_execute.py::_own_position` | Własne zlecenie bez nazwanej pozycji obok pozycji, której nikt nie przypisał, dawało „konto ma obcą pozycję” zamiast niejasności. | FIXED: `unknown` z referencją zlecenia |
| Medium | `strategy_execute.py::_unsupported` | Stop/target/trail czytane z pozycji silnika, której wejście nigdy nie ma. | FIXED: `Signal.exits` z dokumentu (`strategies/signals.py`) |
| Medium | `strategy_execute.py::_signal` | Pytanie co 1 s przez cały termin; każde czyta tydzień archiwum. Narzędzie niedostępne kończyło się `skipped`. | FIXED: odstęp rośnie do 5 s (decyzja D7), niedostępne → `unknown` |
| Low | `steps/catalogue.py` | `deposit_fraction` jako liczba JSON odrzucany przez pole tekstowe. | FIXED: walidator `mode="before"` |
| Low | `teams/store/trades.py` | Odrzucone zlecenia brane za własne. | FIXED: `status <> 'refused'` |

## Spec coverage

| Requirement | Proven by |
|---|---|
| teams-steps: Rewizja może nieść kroki obok agentów; Krok wykonuje przepis z katalogu | `tests/teams/test_steps_definition.py` |
| teams-steps: Krok nie woła modelu i pracuje tą samą drogą co agent; Wynik kroku jest daną | `tests/teams/test_step_attempts.py`, test przebiegu z fałszywymi narzędziami (4.5) |
| teams-steps: Przepis strategy_execute…; Rozmiar pozycji w rewizji; Strategia nieobsługiwana | `tests/teams/test_strategy_execute.py` (tabela `decide` i testy przepisu), `tests/strategies/test_signals.py` (`exits`) |
| teams-steps: Jedna próba na świecę sygnałową | `test_step_attempts.py`, `test_strategy_execute.py` (drugi przebieg po wejściu) |
| teams-steps: Agent może nieść powiadomienie zapasowe | `tests/teams/test_step_fallback.py` (w tym agent padający obok wolnego kroku) |
| teams-usage: Zespół z krokiem wyczerpał granicę dobową | `test_step_fallback.py` |
| terminal-teams: oba wymagania | `modules/terminal/src/teams/TeamsView.test.tsx`, `runs.test.ts` |
| workbench-team-tools: oba wymagania | `tests/teams_tools/test_catalogue_tools.py` |

Pokrycie podane per wymaganie i plik, nie per scenariusz.

## Gaps

- 8.3: próba na produkcji startuje 10 listopada (team 12); wynik i porównanie opóźnienia z teamem 8 (98 s) zapisać w
  `docs/zespoly-kroki-deterministyczne.html`, nie tutaj.
- `db-cost-check` dla odpytywania z odstępem (D7) nie był uruchomiony po zmianie z 1 s na rosnący odstęp; zmiana zmniejsza
  liczbę zapytań, więc klasa kosztu nie rośnie.
- Scenariusz „Zespół z krokiem założony z Telegrama” sprawdzony przez tę samą powierzchnię z Claude Code, nie z Telegrama.
