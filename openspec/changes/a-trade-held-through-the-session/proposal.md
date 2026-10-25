## Why

Operator 25.10.2026 opisał agentowi strategię, której język nie umie zapisać: na US100 decyzja po pierwszej świecy M5
sesji nowojorskiej (zamknięcie powyżej EMA12 → long, poniżej → short), pozycja trzymana do 5 minut przed końcem sesji,
bez SL i TP, depozyt 5% konta. Agent poprawnie odmówił z trzech powodów. Czas w języku jest tylko w UTC, więc godzina
otwarcia Nowego Jorku przesuwa się wobec Polski o godzinę przez około cztery tygodnie w roku. `exits.stop` jest
obowiązkowy, bo wyznacza 1 R. Wielkość pozycji zna tylko ułamek ryzyka i stałe jednostki. To nie są ograniczenia tej
jednej strategii, tylko całej rodziny strategii z wejściem i wyjściem o porze sesji.

## What Changes

- **Sesja w języku.** Rejestr języka dostaje nazwane sesje `NEW_YORK`, `LONDON` i `TOKYO`, ze strefami i godzinami takimi
  jak strefy sesji rysowane na wykresie. Dochodzą dwie funkcje: `session_bar(S)`, czyli numer świecy w dzisiejszej sesji
  liczony zegarem w strefie sesji, oraz `minutes_to_session_close(S)`, czyli minuty od chwili decyzji do zamknięcia
  sesji, ujemne po nim. Zmiana czasu niczego nie przesuwa.
- **Strategia bez stopu.** `exits.stop` staje się opcjonalny. Dokument bez stopu musi mieć wyjście `when` albo
  `max_bars`. Nie może używać niczego, co mierzy się w R: `risk_fraction`, `trail`, `daily_stop_r`, `open_r`,
  `last_trade_r`.
- **Wynik w procentach kapitału obok R.** Każda transakcja niesie wynik w % kapitału przy wejściu i najgłębszą stratę
  otwartą (MAE). Raport dostaje oczekiwaną w %, największą MAE i losowe wejście w %. Bez stopu metryki w R są puste,
  a reszta raportu jest pełna.
- **Wielkość według depozytu i wartości pozycji.** Dochodzą tryby `margin_fraction` (ułamek kapitału jako wymagany
  depozyt) i `notional_fraction` (wartość pozycji jako ułamek kapitału). Wymagany depozyt instrumentu przychodzi od
  brokera, tak jak koszty. Profil instrumentu go pamięta, a uruchomienie zapisuje jego wartość.
- **Brak kapitału zamyka pozycję.** Gdy kapitał wyceniony po stronie wyjścia spada do zera, silnik zamyka pozycję
  (przyczyna `out_of_capital`) i nie otwiera kolejnych. Bez tego strategia bez stopu może pokazać odrobienie straty,
  na które żaden broker by nie pozwolił.
- Wersja schematu dokumentu zostaje 1, bo to same dodatki. Wersja silnika rośnie, bo zmienia się kształt raportu
  i transakcji.

**Poza zakresem:** kalendarz giełdy (święta, skrócone sesje, np. NYSE 3 lipca do 13:00) jest osobną zmianą. Sesja
z tej zmiany zna dni tygodnia i strefę, nie zna świąt. Poza zakresem są też: `hour`/`minute`/`weekday` w strefie innej
niż UTC, sesje definiowane w dokumencie, próg zamknięcia przez brokera (np. 50% depozytu wg ESMA) oraz historia zmian
depozytu.

## Capabilities

### New Capabilities
Brak.

### Modified Capabilities
- `strategies-language`: funkcje sesji w zamkniętej liście funkcji, nazwy sesji jako ich argument; nazwy mierzone w R
  tylko w dokumencie ze stopem.
- `strategies-documents`: stop opcjonalny z warunkiem wyjścia, nowe tryby wielkości, odmowy tego, co bez stopu nie ma
  sensu.
- `strategies-backtest`: wielkość według depozytu i wartości pozycji, wynik w R tylko ze stopem, zamknięcie przy braku
  kapitału, wymagany depozyt od brokera.
- `strategies-reports`: wynik w % i MAE każdej transakcji, metryki w %, losowe wejście w %, depozyt w pochodzeniu
  raportu.
- `strategies-tools` i `strategies-api`: porównanie odmawia uruchomień liczonych z różnym depozytem.
- `terminal-strategies`: transakcja bez stopu na wykresie i depozyt w pochodzeniu wyniku.

## Impact

- `modules/workbench/strategies`:
  - `vocabulary.py`: sesje i dwie funkcje z polskimi sformułowaniami; `checking.py`: nowy rodzaj argumentu;
    `evaluate.py`: wartości sesji przez `zoneinfo`.
  - `document.py`: stop opcjonalny, tryby `sizing`, odmowy.
  - `engine.py`: brak stopu, wielkość, wynik w %, MAE, `out_of_capital`, `ENGINE_VERSION` 3 i ponowne nagranie
    złotych strategii.
  - `reports.py`; `broker_costs.py` i `margins.py` (depozyt); `runs.py`/`queue.py` (depozyt w żądaniu);
    `tools/authoring.py` (`HOW_TO_WRITE` mówi dziś, że stop jest obowiązkowy).
- Migracja `0005`: `run_trades.initial_stop` i `result_r` bez `NOT NULL`, nowe kolumny `result_pct` i `mae_pct`,
  nowa przyczyna wyjścia w `CHECK`, tabela `instrument_margins` (design D5), `return_pct` w `headline`.
- Kontrakt REST (`ReportOut`, `TradeOut`, profil instrumentu) → regeneracja kontraktów terminala skillem
  `contract-sync`. Brama się nie zmienia: `margin_factor` i jego jednostka już są w warunkach instrumentu.
- `modules/terminal`: raport, porównanie i wykres transakcji bez stopu.
- `design.md` powstaje, bo decyzje o sesji, jednostce wyniku bez stopu i źródle depozytu miały realne alternatywy.
  `review.md` powstanie po zadaniach: zmiana rusza silnik, od którego zależy każdy wynik.
