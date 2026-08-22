# Tasks — a-strategy-is-a-catalogue-entry

## 1. Szkielet modułu

- [x] 1.1 Katalog `modules/strategy` wg wzorca polymarket-data: pyproject (editable tc-runtime/tc-mcp-kit), alembic + `migrations/`, pakiet z `app.py`, `config.py`, `runtime.py` (lock 8080), `contract.py`, Dockerfile, README
- [x] 1.2 `config.py` z regułą „tożsamość albo pętla zwrotna" i testami odmów startu (wzorem `test_config.py` polymarket-data)
- [x] 1.3 Lifespan: logging → Settings → pula → advisory lock → migracje → weryfikacja rewizji → pętla → sesja `/mcp`; testy migracji pod lockiem
- [x] 1.4 `scripts/dev.py`: wiersz w `SERVICES` (8080), `strategy` w `LOGICAL_DATABASES`, wpis w `MIGRATION_CHAINS`; `grant-schema-ownership.sql` odnotowany w README modułu

## 2. Kontrakt wpisu i katalog strategii

- [x] 2.1 Typy kontraktu: `StrategySpec` (fakty, parametry z zakresami, `evaluate`), `Fact`, `Decision` (akcja, powód, poziomy, cechy, wersja parametrów)
- [x] 2.2 Rejestr wpisów + walidacja przy rejestracji (parametry w zakresach, wskaźniki ogłaszane przez archiwum)
- [x] 2.3 Test warstwy: dodanie wpisu nie zmienia runtime; `evaluate` bez we/wy i zegara (test, nie konwencja)
- [x] 2.4 Wpis baseline na istniejących wskaźnikach archiwum, z testami na ręcznych faktach

## 3. Runtime

- [ ] 3.1 Klient market-data: świece + `POST /indicators`, cięcie okien pod sufit 200k barów, mapowanie niedopokrycia
- [ ] 3.2 Pętla na domkniętych świecach: fakty → bramki wspólne → `evaluate` → zapis; odmowa „pokrycie" odróżnialna od odmowy strategii
- [ ] 3.3 Magazyn: zestawy parametrów (wersjonowane, niezmienne), decyzje ze snapshotem faktów; test odtworzenia decyzji z zapisu
- [ ] 3.4 Stany: start bez aktywnych strategii, dezaktywacja jednej nie zatrzymuje reszty; test, że moduł nie ma klienta konta

## 4. Powierzchnie

- [ ] 4.1 REST: strategie, zestawy parametrów, decyzje (lista/szczegół z powodami); trzy testy na widok
- [ ] 4.2 `/mcp` read-only: `pending_setups(strategy)`, `last_decision`, lista strategii; test „zestaw wyłącznie czyta"
- [ ] 4.3 Tożsamość wołającego (`caller_access` wzorem polymarket-data) + test odmowy spoza listy
- [ ] 4.4 Ręczna próba szwu: wyzwalacz workbencha na `pending_setups` budzi zespół na kandydacie baseline

## 5. Backtest

- [ ] 5.1 Sterownik odtwarzania wołający `evaluate` pętli; test przyrostowe = wsadowe; test „dłuższy zakres nie zmienia wspólnej części"
- [ ] 5.2 Symulator wypełnień + model kosztów jako jawny parametr; raport nazywający koszty, wersję parametrów i zakres
- [ ] 5.3 Metryki (expectancy R, profit factor, obsunięcie, seria strat) + atrybucja po cechach decyzji
- [ ] 5.4 Porównanie strategii: wspólne dane i koszty albo odmowa; komenda `python -m strategy.backtest`
- [ ] 5.5 Backfill historii instrumentów docelowych jobami archiwum i kontrola `coverage` (operacyjne, nie kod)

## 6. Wdrożenie

- [ ] 6.1 `infra/`: App Service, tożsamość zarządzana, baza `strategy`; tożsamość modułu w `allowed_applications` i `REST_CALLER_APPLICATION_IDS` market-data
- [ ] 6.2 CI: job modułu w `checks.yml`; `deploy-strategy.yml` z sondą `deploy_probe.py`
- [ ] 6.3 Kolejność produkcyjna: apply przed obrazem (jak przy narzędziach workbencha); próba odwrotu — dezaktywacja strategii i usunięcie wyzwalacza
