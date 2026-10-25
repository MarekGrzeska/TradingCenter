## 0. Przed pracą

- [x] 0.1 Zarchiwizować `a-strategy-is-a-document` (sync specyfikacji, `scripts/trim-openspec-archive.sh`) i powtórzyć `openspec validate a-strategy-from-a-description --strict`

## 1. Pakiet: dokumenty, koszty, raport

- [x] 1.1 Migracja `0002`: `cost_profiles (symbol PK, costs jsonb, updated_at)` i `runs.requested_by` (`operator`/`agent`, domyślnie `operator`); test migracji pod blokadą (`-m db`)
- [x] 1.2 Profile kosztów: zapis i odczyt przez `CostModel`, trasy `GET /costs`, `GET`/`PUT /costs/{symbol}`; testy wg reguły CRUD
- [x] 1.3 Zapis z rewizją bazową (`based_on`) i 409 z numerem ostatniej rewizji; treść równa ostatniej nie jest konfliktem
- [x] 1.4 `GET /strategies/{id}/revisions` (bez dokumentów) i `changes.py` z `GET /strategies/{id}/revisions/{n}/changes?against=`; testy jednostkowe różnic (kolejność kluczy, dodane/usunięte, pierwsza rewizja)
- [x] 1.5 `summary.py`: sformułowania w rejestrze `vocabulary.py`, test odmawiający funkcji bez sformułowania, interwały w nazwach terminala, godziny UTC z polską zimą i latem, `hypothesis`/`notes` dosłownie; streszczenie w `POST /validate` i w odczytach rewizji
- [x] 1.6 Krzywa dzienna w `reports.build`, `ENGINE_VERSION` 2, ponowne nagranie złotych strategii; test, że obsunięcie % z krzywej równa się raportowemu
- [x] 1.7 `ReportOut` w `contract.py` (pola `strategies-reports`, `equity` opcjonalne dla v1) i główne metryki oraz `requested_by` w `RunSummaryOut` (odczyt z `report` w SQL)

## 2. Narzędzia w rozmowie

- [x] 2.1 Sygnał zakończenia uruchomienia w kolejce (`queue.py`), na który można poczekać z limitem czasu
- [x] 2.2 `mcp_app.py` i `tools/` z ośmioma narzędziami z `strategies-tools`; serwer w `app.state.mcp_server`, niemontowany pod `/mcp`
- [x] 2.3 `save_strategy` z autorem `agent`, podstawą, streszczeniem i zmianami; `run_backtest` z kosztami z profilu, `requested_by = agent`, jednym uruchomieniem agenta naraz i oczekiwaniem; `compare_runs` z odmową przy różnym zakresie, kosztach albo wersji silnika
- [x] 2.4 `workbench/app.py`: `ConversationLocalTools("strategies", …)` tylko gdy pakiet zamontowany; nie w `teams_tool_servers.local`, nie w `AlertTools`
- [x] 2.5 Testy powierzchni: zestaw nazw, opisy (`notes`, próby, brak szukania parametrów), sufit znaków z pomiaru, brak narzędzia profilu kosztów; test, że zespoły i katalog alertów nie widzą narzędzi strategii i że `/strategies/mcp` nie odpowiada

## 3. Rozmowa: otwarta strategia w kontekście tury

- [x] 3.1 `SendMessageIn.strategy` (identyfikator, rewizja, tekst z sufitem i odmową 422 ponad sufit) i jego zdanie kontekstu w `turn._system_prompt`; test, że nie trafia do transkryptu
- [x] 3.2 Skill `contract-sync`: nowy `contract.strategies.generated.ts` w terminalu (źródło w `scripts/contract.mjs`), kontrakt agenta w terminalu i w pocket

## 4. Terminal: zakładka Strategies

- [x] 4.1 `VITE_STRATEGIES_HTTP` w `config.ts`, proxy `/strategies-api` w `vite.config.ts`, `deploy-vps.yml`; klient `strategiesApi.ts` z mapowaniem kontraktu
- [x] 4.2 Wpis w `tabs.ts` (grupa `trading`, ładowany leniwie); lista strategii z archiwizacją i komunikatem o braku pakietu
- [x] 4.3 Edytor CodeMirror 6: JSON, podpowiedzi z `GET /language` i z dokumentu (interwał z nazwą terminala obok), walidacja po przerwie tylko dla zmienionego tekstu i widocznej zakładki, problemy w miejscu ścieżki i kolumny
- [x] 4.4 Zapis z podstawą i wyborem przy 409; streszczenie obok z oznaczeniem nieaktualności
- [x] 4.5 Historia rewizji ze zmianami i przywróceniem jako kolejna rewizja
- [x] 4.6 Współpraca z panelem: `strategy` w żądaniu tury z zakładki na ekranie, odczyt po `agentActivity`, wczytanie rewizji agenta bez nadpisania niezapisanych zmian, otwarcie strategii utworzonej w turze
- [x] 4.7 Formularz uruchomienia (zakres w dniach polskich, parametry, koszty z profilu, licznik minut wobec sufitu) i edycja profilu kosztów
- [x] 4.8 Lista uruchomień: stan, zlecający, główne metryki, odświeżanie tylko przy czekających, anulowanie
- [x] 4.9 Raport: metryki z pustymi jako brak wartości, punkty odniesienia, koszty, pochodzenie, krzywa z obsunięciem (albo zdanie dla v1), lista transakcji stronami
- [x] 4.10 Znaczniki transakcji w `Chart` i wykres ceny w raporcie; wybór transakcji ustawia kadr i rysuje wejście, wyjście i stop
- [x] 4.11 Testy wg reguły CRUD dla listy, edytora i formularza; testy jednostkowe mapowania ścieżki i kolumny na pozycję w tekście oraz decyzji „wczytać czy zachować” po turze

## 5. Koszt, dokumentacja, wdrożenie

- [x] 5.1 Skill `db-cost-check` dla walidacji na żywo, odświeżania listy uruchomień i metryk w `GET /runs`
- [x] 5.2 `strategies/README.md` (narzędzia, profile kosztów, streszczenie, „No tools yet” znika), `modules/workbench/README.md`, tabela w `CLAUDE.md`, `docs/architecture.md`
- [ ] 5.3 Po merge skill `deploy-watch`; profile kosztów dla instrumentów zbieranych na `MINUTE`
- [x] 5.4 `review.md`
