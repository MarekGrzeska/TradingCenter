## 1. Sesja w języku

- [x] 1.1 `vocabulary.py`: `SESSIONS` (strefa, otwarcie, zamknięcie, pon.–pt.), `Arg.SESSION`, `session_bar` i `minutes_to_session_close` z sformułowaniami; nazwy sesji w `RESERVED` i `NAME_PHRASES`
- [x] 1.2 `checking.py`: argument sesji przyjmuje tylko nazwę sesji; nazwa sesji poza nim i funkcja sesji w kontekście `DAY`/`WEEK` (także przez `@`) to błąd w ścieżce
- [x] 1.3 `evaluate.py`: otwarcie i zamknięcie w UTC raz na dzień przez `zoneinfo`, przypisanie świecom wektorowo (D2); `minutes_to_session_close` od `available`, ujemne po zamknięciu, puste w dzień bez sesji (D3); `requirements.py` bez rozgrzewki dla funkcji sesji
- [x] 1.4 `summary.py`: sesja nazwana z godzinami lokalnymi i polskimi (zwykle 15:30–22:00 dla Nowego Jorku) oraz „bez świąt giełdowych”
- [x] 1.5 Testy jednostkowe scenariuszy `strategies-language` (2.07, 27.10 i 1.12.2026, brak świecy otwarcia, −10 po zamknięciu, odmowy); zgodność wektorowa z liczeniem świeca po świecy już obejmuje nowe funkcje
- [x] 1.6 `tests/test_session_hours_agree.py`: sesje języka wobec `_SESSION_TYPES` katalogu wykresu

## 2. Dokument bez stopu i nowe tryby wielkości

- [x] 2.1 `document.py`: `ExitsIn.stop` opcjonalny; `SizingIn.mode` z `margin_fraction` (wartość ≤ 1) i `notional_fraction`; bez stopu wymagane `when` albo `max_bars` i osobny błąd dla `risk_fraction`, `trail`, `daily_stop_r`, `open_r`, `last_trade_r`; usunięty komunikat „a strategy needs a stop”
- [x] 2.2 Testy scenariuszy `strategies-documents`: strategia sesyjna operatora przyjęta, dwa błędy dla `risk_fraction` z `open_r`, brak stopu i wyjścia odrzucony

## 3. Silnik

- [x] 3.1 `engine.py`: pozycja bez stopu (`risk` puste, bez sprawdzania stopu i trailingu), `result_r` puste, `result_pct` od kapitału przy wejściu, `mae_pct` w pętli minut
- [x] 3.2 Wielkość `margin_fraction` i `notional_fraction` z depozytem podanym do `simulate`
- [x] 3.3 `out_of_capital`: poziom zerowego kapitału z narosłym finansowaniem na każdej minucie, luka po pierwszej cenie, potem bez wejść do końca zakresu (D6)
- [x] 3.4 `losses_in_row` z pieniądza; `ENGINE_VERSION = 3`; złota strategia sesyjna bez stopu w `tests/strategies/golden/` i ponowne nagranie wszystkich
- [x] 3.5 Testy scenariuszy `strategies-backtest`: wyjście 19:55 UTC 2.07.2026, 0,5 jednostki w obu trybach, wynik 1,5% bez R, `out_of_capital` po 10 000 i brak dalszych wejść

## 4. Depozyt od brokera

- [x] 4.1 Na demo (`-m live --run-live`): `margin_factor` i jednostka w warunkach US100, US500, GOLD i EURUSD; wynik w design.md D5
- [x] 4.2 Migracja `0005`: `run_trades.initial_stop`/`result_r` bez `NOT NULL`, `result_pct`, `mae_pct`, `CHECK` z `out_of_capital`, tabela `instrument_margins` (D5); `downgrade` z odmową przy transakcjach bez stopu
- [x] 4.3 `broker_costs.py`: odczyt depozytu z warunków (procenty → ułamek, inna jednostka albo brak = odmowa z nazwą); `margins.py`: depozyt pobrany i trzymany; `GET`/`PUT /margins/{symbol}` dla operatora
- [x] 4.4 `runs.py`/`queue.py`: depozyt rozstrzygany przy kolejkowaniu tylko dla `margin_fraction`, kopiowany do `request` i podawany workerowi
- [x] 4.5 Testy `-m db`: pierwsze uruchomienie zapisuje depozyt, a profil kosztów się nie zmienia, jednostka `POINTS` to odmowa bez zapisu, `fixed_units` bez odczytu depozytu

## 5. Raport i kontrakt

- [x] 5.1 `reports.py`: zyskowność, profit factor i serie z pieniądza; `expectancy_pct`, `worst_mae_pct`, lata w R i %, losowe wejście w %; metryki R puste bez stopu; `return_pct` w `headline`
- [x] 5.2 `contract.py`: `ReportOut`, `TradeOut` (`initial_stop`/`result_r` opcjonalne, `result_pct`, `mae_pct`, `out_of_capital`), `HeadlineOut`, profil z depozytem; depozyt w pochodzeniu raportu
- [x] 5.3 Testy scenariuszy `strategies-reports` (strategia bez stopu, MAE −1% i +0,5%, losowe wejście w %, depozyt w raporcie)
- [x] 5.4 `tools/authoring.py`: `HOW_TO_WRITE` bez „stop is required”, z sesjami i trybami wielkości; sufit powierzchni narzędzi

## 6. Terminal

- [x] 6.1 Skill `contract-sync`: kontrakty strategii
- [x] 6.2 `ReportPanel` i `ComparePanel`: metryki w %, pusty R jako brak wartości, depozyt w pochodzeniu; lista transakcji z wynikiem w %
- [x] 6.3 Wykres transakcji bez linii stopu, gdy transakcja go nie ma; test scenariusza „Transakcja bez stopu”

## 7. Dokumentacja i wdrożenie

- [x] 7.1 `strategies/README.md`: przykład z sesją, „A stop is required” zastąpione zasadą bez stopu, tryby wielkości, `out_of_capital`
- [x] 7.2 `openspec validate a-trade-held-through-the-session --strict`
- [ ] 7.3 Po merge skill `deploy-watch`; na produkcji agent zapisuje strategię operatora z 25.10 i uruchamia ją na US100
- [ ] 7.4 `review.md`
