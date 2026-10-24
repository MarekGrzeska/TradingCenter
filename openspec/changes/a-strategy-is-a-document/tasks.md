## 1. Szkielet pakietu i baza

- [x] 1.1 `strategies/` z `config.py` (prefiks `STRATEGIES_`: baza, pula 2, lista aplikacji REST, `RUN_CONCURRENCY`, `MAX_MINUTE_BARS`, limit czasu uruchomienia, powtórzenia losowego wejścia), `runtime.py` (klucz blokady `8130`), `app.py`, `openapi.py`, `caller_access.py` (ścieżki zapisane wprost)
- [x] 1.2 `alembic-strategies.ini` i migracja: `strategies`, `strategy_revisions` (PK `(strategy_id, n)`, dokument, hash treści, schemat, autor), `runs` (wkład, wersja silnika, stan, przyczyna, czasy, raport, pochodzenie), `run_trades` (stronicowane po `(run_id, seq)`)
- [x] 1.3 Montaż warunkowy w `workbench/app.py`, wpis w `tests/test_layering.py` i `scripts/tests/test_pool_budget.py`, blok `STRATEGIES_*` w `.env.example`
- [x] 1.4 `scripts/dev.py` (`LOGICAL_DATABASES`, łańcuch opcjonalny), `deploy/postgres/ensure-databases.sh` (`ensure strategies`), `deploy/docker-compose.yml`, `deploy/env.required` (`STRATEGIES_DB_PASSWORD`), `deploy/scripts/backup.sh` i `backup-check.sh`; test w `scripts/tests`, że żadna nazwa z `ensure` nie jest w `retire`
- [x] 1.5 Testy: start bez bazy, baza nieosiągalna (odmowa z nazwą), migracja pod blokadą (`-m db`)

## 2. Język formuł

- [x] 2.1 Parser: `ast.parse(mode="eval")`, biała lista węzłów, sufit długości i głębokości; test na każdy typ węzła spoza listy i test, że źródło pakietu nie woła `eval`/`exec`/`compile`
- [x] 2.2 Rejestr funkcji własnych (sygnatury, typy, gdzie dozwolone) jako jedno źródło dla walidatora i `GET /language`
- [x] 2.3 Funkcje katalogu z `GET /market/indicators`: tylko wyjście liniowe, parametry pozycyjnie i po nazwie, zakresy z katalogu, wybór linii polem
- [x] 2.4 Sprawdzanie nazw i typów: zmienne `let` (cykle, przesłanianie), `p.*` wobec `params`, stan pozycji tylko w wyjściach, `@` z rozdzielczością albo symbolem, przesunięcia i okna w granicach; błędy ze ścieżką, kolumną i podpowiedzią najbliższej nazwy
- [x] 2.5 Testy jednostkowe walidacji: każdy powód odrzucenia raz, każda konstrukcja przyjęta raz

## 3. Dokumenty i rewizje

- [x] 3.1 Model dokumentu (sekcje z `strategies-documents`, pola nieznane jako odmowa, stop obowiązkowy, `schema`)
- [x] 3.2 Walidacja zależna od archiwum: symbol i rozdzielczość dostępne, `MINUTE` instrumentu handlowanego (odczyt `/market` w procesie)
- [x] 3.3 Zapis: rewizja n+1 z hashem, brak rewizji przy treści równej ostatniej, archiwizacja i przywrócenie, brak usuwania
- [x] 3.4 Testy: rewizje niezmienne, ponowny zapis tej samej treści, dokument ze schematu przyszłego (`-m db` tylko tam, gdzie zapis)

## 4. Silnik backtestu

- [x] 4.1 Odczyt serii z `/market` w procesie w miesięcznych porcjach: świece (bez formujących), wskaźniki per kontekst, chwila dostępności, rozgrzewka, fragmenty niepotwierdzone, odcisk danych
- [x] 4.2 Faza wektorowa: serie, przesunięcia, okna, zdarzenia, czas, dopasowanie `@` po chwili dostępności, `stale`
- [x] 4.3 Broker na `MINUTE`: ask z profilu spreadu, zlecenia `market`/`stop`/`limit` z wygaśnięciem, jedna pozycja i jedno oczekujące zlecenie, stop/cel/trailing/`when`/`max_bars`, luki, rozstrzyganie pesymistyczne z oznaczeniem, koniec zakresu
- [x] 4.4 Faza stanowa: interpreter formuł ze stanem pozycji i historią, `at_entry`, `daily_stop_r`, `no_entry`
- [x] 4.5 Rozmiar (`risk_fraction`, `fixed_units`), wynik w R i w pieniądzu nominalnym (design D6), finansowanie overnight za każde przekroczenie godziny rozliczenia
- [x] 4.6 Testy jednostkowe: każdy scenariusz z `strategies-backtest` raz, na najniższej warstwie; test „naraz = świeca po świecy” i „dłuższy zakres nie zmienia wcześniejszych transakcji”
- [x] 4.7 Pomiar na danych dev (rok `MINUTE` US100): czas i pamięć jednego uruchomienia, z tego domyślne limity w `config.py` (design, Open Questions)

## 5. Uruchomienia jako zadania

- [x] 5.1 `POST /runs`: walidacja wkładu (parametry w zakresach, model kosztów obowiązkowy, limit świec przed zakolejkowaniem), zapis w stanie zakolejkowanym
- [x] 5.2 Kolejka w lifespanie: osobny proces `spawn` na uruchomienie (design D5), limit czasu, anulowanie, przy starcie `running` → niepowodzenie „przerwane restartem”
- [x] 5.3 Test, że uruchomienie w toku nie opóźnia odpowiedzi `/market/ping` i trasy pakietu obok (`workbench-process`)
- [x] 5.4 `db-cost-check` dla odczytu roku `MINUTE` z porcjami i dla zapisu `run_trades`

## 6. Raport

- [x] 6.1 Metryki z `strategies-reports` (puste zamiast zera, metoda rocznej skali Sharpe'a nazwana), podział na lata, koszty na składniki, wynik bez pięciu najlepszych
- [x] 6.2 Punkty odniesienia: kup i trzymaj, losowe wejście z ziarnem (mediana, 5. i 95. percentyl)
- [x] 6.3 Pochodzenie: rewizja i hash, wkład, wersja silnika, ziarno, odciski danych, fragmenty niepotwierdzone; licznik prób na strategię
- [x] 6.4 Testy jednostkowe metryk na ręcznie podanych transakcjach; test, że raport nie ma pola oceny

## 7. REST

- [x] 7.1 Trasy z `strategies-api`, `GET /language` z rejestru i katalogu, `POST /validate` bez zapisu, `GET /health`
- [x] 7.2 Testy wg reguły CRUD (szczęśliwa ścieżka, błąd, odmowa) dla strategii i uruchomień; odmowa dla `viewer`; test zależności pakietu bez klienta bramy i `trading-mcp`

## 8. Złote strategie

- [ ] 8.1 Generator świec z ziarnem, nagranie odpowiedzi `/market/indicators`, 4–6 dokumentów referencyjnych (konstrukcje języka, typy zleceń, luki, rozstrzygnięcia pesymistyczne, finansowanie, inny interwał i instrument)
- [ ] 8.2 `ENGINE_VERSION`, test porównujący wyniki i wersję, skrypt regenerujący, który odmawia bez podniesienia wersji

## 9. Dokumentacja i wdrożenie

- [ ] 9.1 `strategies/README.md`; `modules/workbench/README.md`, tabela pakietów i klucze blokad w `CLAUDE.md`, `docs/architecture.md`; przykład w `docs/strategie-i-backtesty-research.html` w formie katalogu (`ema(20)`, nie `ema(close, 20)`)
- [ ] 9.2 `STRATEGIES_DB_PASSWORD` w środowisku GitHub `vps` przed merge (`fill-github-environment.sh`)
- [ ] 9.3 Po merge skill `deploy-watch`; skrypty kopii zainstalowane na serwerze i sprawdzony nocny zrzut z `strategies`
- [ ] 9.4 `review.md`
