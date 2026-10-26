## 1. Silnik i sygnał

- [x] 1.1 `engine.py`: `Result.in_flight` — zlecenie i pozycja po ostatniej decyzji, przed rozliczeniem do końca zakresu; golden bez zmian
- [x] 1.2 Nowy `signals.py`: okno (D2), odczyt przez `reading.read`, koszty i depozyt (D3), `simulate` w wątku z limitem (D4), odpowiedź ze specu; odmowy: brak strategii/rewizji, brak depozytu, luka na ostatniej świecy
- [x] 1.3 Testy jednostkowe: wejście na pierwszej świecy sesji NY; wyjście należne; brak działania; zgodność z transakcjami `simulate` na tym samym odcinku (sygnał po każdej świecy)

## 2. Narzędzia

- [x] 2.1 `tools/`: `strategy_signal` (opis: sprawdź wiek świecy, wielkość licz z salda przez `size_for_margin`)
- [x] 2.2 `mcp_app.py`: serwer czytający dla zespołów (D5); test, że ogłasza dokładnie trzy narzędzia
- [x] 2.3 Test: wywołanie sygnału nie zmienia licznika prób ani listy uruchomień (`-m db`)
- [x] 2.4 Sufit powierzchni narzędzi strategii (`tests/strategies/test_tools.py`) — zmierzony, podniesiony świadomie, jeśli trzeba

## 3. Montaż

- [x] 3.1 `workbench/app.py`: `teams_tool_servers.local["strategies"]` z serwera czytającego, gdy pakiet zamontowany
- [ ] 3.2 Test: katalog zespołów (`GET /teams/tools`) ma trzy narzędzia strategii i żadnego zapisującego; bez pakietu — żadnego (luka, `review.md`)

## 4. Dokumentacja i domknięcie

- [x] 4.1 README pakietu (sekcja narzędzi), `CLAUDE.md` (mapa `modules/workbench`), README workbench, jeśli wymienia
- [x] 4.2 `openspec validate strategy-signal-for-teams --strict`; `review.md`
