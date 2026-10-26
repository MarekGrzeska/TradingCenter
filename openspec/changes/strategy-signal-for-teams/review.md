## Verdict

Wszedł `strategy_signal` — decyzja silnika backtestu dla wskazanej rewizji, liczona tym samym `simulate` na oknie 2 000
świec i odczytana przed rozliczeniem tego, co w toku — oraz czytający serwer strategii dla zespołów z trzema narzędziami.
Reguła „narzędzia strategii tylko dla rozmowy” jest zmieniona w CLAUDE.md, README workbench i README pakietu. Świadomie
niepełne: montaż w `workbench/app.py` (rejestr zespołów dostaje serwer czytający) nie ma testu na poziomie całego procesu.

## Verified

- `uv run pytest tests/strategies tests/test_tool_names.py tests/test_layering.py tests/teams/test_tools_route.py -m "db or not db"`
  — 284 passed (26 października 2026).
- `tests/strategies/test_golden.py` w tym przebiegu — wyniki backtestów niezmienione, `ENGINE_VERSION` zostaje 4.
- `ruff check .` czysty; `pyright strategies` — 0 errors.
- Powierzchnia narzędzi rozmowy zmierzona lokalnie: 12 238 → 13 214 znaków; sufit podniesiony z 13 500 do 14 500 z
  zapisanym pomiarem. Serwer zespołów: 3 548.

## Findings

| Severity | Where | Finding | Status |
|---|---|---|---|
| Średnia | `strategies/tools/signal.py` | Typowana odpowiedź (`Signal` z zagnieżdżonymi modelami) dokładała ponad 2 000 znaków schematu wyjścia do każdej tury i przebijała sufit. | FIXED przed commitem: narzędzie oddaje słownik, pola wymienia opis (jak `read_backtest`). |
| Niska | `strategies/signals.py` | Limit czasu (`asyncio.wait_for` na `to_thread`) przestaje czekać, ale nie zatrzymuje wątku — przekroczony sygnał liczy się dalej w tle. Okno M5 liczy się w ułamku sekundy, więc nie ma dziś ścieżki, na której to boli. | Otwarte, świadomie. |

## Spec coverage

| Requirement / Scenario | Proven by |
|---|---|
| Powierzchnia narzędzi pakietu strategii | `tests/strategies/test_tools.py::test_the_surface_is_the_twelve_tools_and_none_sets_costs`, `::test_the_surface_stays_under_its_ceiling` |
| — Pakiet nieobecny / Nowy wskaźnik / Odczyt usuniętego | bez zmian względem dotychczasowych testów pakietu |
| Zespoły dostają tylko narzędzia strategii do odczytu — Narzędzia dla agenta zespołu | `tests/strategies/test_tools.py::test_a_team_gets_the_three_that_read_and_nothing_that_writes` (serwer); montaż w procesie — luka |
| — Pakiet nieobecny w zespołach | luka (montaż decydowany przy imporcie `workbench.app`) |
| Sygnał strategii jest decyzją silnika — Pierwsza świeca sesji nowojorskiej | `tests/strategies/test_signals.py::test_the_first_new_york_bar_closing_is_a_market_entry_signalled_on_it` (bez EMA: wskaźniki przychodzą z archiwum, test silnika ich nie ma) |
| — Ta sama decyzja co backtest | `tests/strategies/test_signals.py::test_every_trade_of_a_backtest_is_a_signal_on_the_same_bar` |
| — Sygnał nie jest próbą | `tests/strategies/test_signals.py::test_the_signal_reads_the_archive_and_writes_nothing`, `tests/strategies/test_tools.py::test_a_signal_with_no_closed_bar_is_a_refusal_naming_the_gap_and_counts_nothing` |
| — Brak świecy w archiwum | `tests/strategies/test_tools.py::test_a_signal_with_no_closed_bar_is_a_refusal_naming_the_gap_and_counts_nothing` |

## Gaps

- Montaż serwera czytającego w rejestrze zespołów (`workbench/app.py`) i jego brak bez pakietu — nie ma testu procesu z
  zamontowanym pakietem strategii (tak samo jak dla alertów i YouTube). Pierwszy dowód: `list_tools` zespołów na
  produkcji po wdrożeniu.
- Scenariusz z EMA12 jest sprawdzony na warunku sesji bez wskaźnika; zgodność wskaźników z archiwum trzyma golden
  silnika i odczyt `reading.read`, wspólny z backtestem.
