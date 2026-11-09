## 1. Kontrakt i walidacja definicji

- [x] 1.1 `StepDefinition` (`key`, `recipe`, `params`) i `steps: list = []` w `TeamDefinition`; walidatory grafu na sumie kluczy agentów i kroków, „co najmniej jeden węzeł”; test, że rewizja bez `steps` czyta się bez zmian
- [x] 1.2 `fallback_notice` (`destination`, `bot`, `prefix`) w `AgentDefinition`, opcjonalne
- [x] 1.3 Katalog przepisów (`teams/steps/`): model parametrów, narzędzia, opis; `strategy_execute` z parametrami `strategy_id`, `revision`, `symbol`, `sizing` (opcjonalne), `wait_for_bar_seconds` (opcjonalne, 30), `max_bar_age_seconds` (opcjonalne)
- [x] 1.4 `check_definition`: nieznany przepis, złe parametry, nieogłaszane narzędzie przepisu, zakaz narzędzi przełączających konto, `fallback_notice` bez `send_telegram_message`; każda odmowa nazywa krok albo agenta
- [x] 1.5 `GET /teams/step-recipes` (nazwa, opis, parametry z typem i wymaganiem, narzędzia); `contract-sync` dla terminala

## 2. Baza

- [x] 2.1 Migracja łańcucha `teams`: `trades.attempt_key text` i częściowy indeks unikalny `WHERE attempt_key IS NOT NULL`; `record_trade` z kluczem, konflikt jako osobny wynik
- [x] 2.2 Odczyt własnych wierszy `place_order` zespołu (zespół, właściciel, symbol, rozliczone), na potrzeby przepisu; `db-cost-check` dla tego zapytania i dla czekania na świecę

## 3. Przebieg: węzeł kroku

- [x] 3.1 Wydzielić z `_StepRunner` wspólną ścieżkę wywołań węzła (`run_steps`, `tool_calls`, `TradeGuard`, wiersz `trades` przed wysłaniem, rozliczenie); agent bez zmian w zachowaniu, testy agenta zielone
- [x] 3.2 `plan_tools`: narzędzia przepisu pod kluczem kroku; `create_run` z kluczami agentów i kroków
- [x] 3.3 `compile_team`: węzeł kroku obok węzła agenta, wynik kroku (JSON) jako praca poprzednika; zdarzenia postępu dla kroku
- [x] 3.4 Krok: wynik przewidziany przez przepis kończy krok jako zakończony; nieprzewidziany wyjątek kończy go błędem i zatrzymuje przebieg

## 4. Przepis strategy_execute

- [x] 4.1 `decide(...)` jako czysta funkcja: wejście, zamknięcie, pominięcie, odmowa, wynik nieznany, strategia nieobsługiwana; tabela przypadków ze specyfikacji (świeża i stara świeca, brak `max_bar_age_seconds`, pozycja ręczna, pozycja własna i silnik płaski albo przeciwny, pozycja starsza niż okno, stop w dokumencie)
- [x] 4.2 Odczyty: `strategy_signal` z ponawianiem co 1 s do terminu, potem równolegle konto, pozycje, zlecenia, saldo i własne wiersze zespołu
- [x] 4.3 Zapis: `size_for_margin` z depozytem z dokumentu albo kroku, `place_order` rynkowe z kluczem próby, `close_position` dla własnej pozycji, potwierdzenie `get_positions`; bez ponowień przy wyniku nieznanym
- [x] 4.4 Wynik: decyzja, powód, `summary`, rozmiar i źródło, zlecenie, znaczniki czasu, poślizg względem otwarcia minuty przyjętego przez backtest
- [x] 4.5 Jeden test na przebieg: krok na fałszywych narzędziach składa zlecenie, wiersz `trades` z kluczem i `tool_calls` przy kroku, zero wierszy zużycia; drugi przebieg tej samej świecy kończy się pominięciem

## 5. Powiadomienie zapasowe i granica kosztu

- [ ] 5.1 Węzeł agenta z `fallback_notice`: przy błędzie modelu albo granicy kosztu jedna wiadomość (prefiks, `summary` kroków-poprzedników, powód) przez jego `send_telegram_message`, w jego śladzie; status przebiegu bez zmian
- [ ] 5.2 `start_run_on_revision`: rewizja z krokami przy wyczerpanej granicy dobowej rusza, agenci dostają wyczerpany `CostGuard` z powodem dobowym; rewizja bez kroków odmawiana jak dziś; testy obu

## 6. tc-team-tools

- [ ] 6.1 `create_team` z `steps` i `trading`; `revise_team` z `replace_steps`, `remove_step_keys` i `trading`; `read_team` zwraca `steps`
- [ ] 6.2 `trading` z czatu: tylko `environment=demo`; zmiana sekcji `trading` rewizji na koncie realnym odmówiona z odesłaniem do terminala; przeniesienie bez zmian, gdy nie nazwana
- [ ] 6.3 `list_step_recipes` (odczyt); opisy narzędzi: krok nie woła modelu, wynik czyta następnik; sufit powierzchni podniesiony świadomie o zmierzoną wartość

## 7. Terminal

- [ ] 7.1 Krok na obrazie zespołu odróżniony od agenta, z nazwą przepisu i rozmiarem przy węźle; rozmieszczenie zapisywane jak dla agenta
- [ ] 7.2 Dodanie kroku z wyborem przepisu z katalogu, formularz parametrów z katalogu, „z dokumentu strategii” przy pustym rozmiarze, usuwanie, zależności; `fallback_notice` w panelu agenta; odmowa przy kroku
- [ ] 7.3 Przebieg: stan kroku, decyzja i `summary` nad pełnym wynikiem, wywołania i zlecenia przy kroku, powiadomienie zapasowe przy agencie; trzy testy widoku (zespół z krokiem, odmowa zapisu przy kroku, przebieg z wynikiem kroku)

## 8. Dokumentacja i próba

- [ ] 8.1 `modules/workbench/README.md` (kroki w `teams`), `docs/zespoly-kroki-deterministyczne.html` odsyła do tej zmiany
- [ ] 8.2 Na demo przed pierwszym zespołem: `id` z `place_order` porównany z id pozycji w `get_positions` (decyzja 5 projektu)
- [ ] 8.3 Operator: zespół demo z krokiem i reporterem założony z Telegrama, na innym koncie demo niż team 8, harmonogramy 9:35, 14:00 i 14:10 ET; tydzień porównania z teamem 8
- [ ] 8.4 `review.md`; archiwizacja
