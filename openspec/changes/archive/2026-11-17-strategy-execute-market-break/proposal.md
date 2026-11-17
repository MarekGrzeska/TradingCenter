## Why

Noga 5 strategii 68 (noc po słabym dniu, team 14) decyduje na świecy M5 zamykającej się o 17:00 w Nowym Jorku
(22:00 UTC zimą), a backtest wchodzi na otwarciu następnej świecy. Capital.com ma na US100 codzienną przerwę
22:00–22:05 UTC: w archiwum nigdy nie ma świecy 22:00. 16.11.2026 krok `strategy_execute` wystartował o 22:00:06,
pytał o sygnał przez 60 s i skończył się pominięciem („the archive has no MINUTE_5 bar closing at 22:00”). Świeca
21:55 dotarła do archiwum o 22:01:58: bramka oddaje świecę jako zamkniętą dopiero, gdy dostawca zacznie następną, a w
przerwie nie zaczyna — kolektor uzupełnia ją z historii po 120 s ciszy. Silnik tego wieczoru wszedł long po 27 166,5
o 22:05; konto demo nie.

Dłuższe czekanie samo nie wystarczy: świeca jest w archiwum o 22:02, a rynek jest zamknięty do 22:05, więc zlecenie
wysłane od razu trafiłoby w przerwę.

## What Changes

- `strategy_execute` przed zleceniem (wejściem i zamknięciem) czeka, aż rynek poda cenę po zamknięciu świecy
  sygnałowej, w tym samym czasie czekania, który dziś obejmuje tylko świecę. W zwykłej sesji cena jest od razu i nic
  się nie zmienia; po świecy przed przerwą zlecenie idzie po wznowieniu notowań — tam, gdzie wykonuje je backtest.
- Wielkość jest liczona z tej pierwszej ceny po przerwie.
- Gdy rynek nie wznowi notowań w czasie czekania: pominięcie bez zlecenia, z powodem.
- Górna granica czasu czekania rośnie ze 120 do 600 s.
- Porównanie z backtestem (`vs_backtest.assumed_open`) bierze pierwszą minutę od zamknięcia świecy, a nie tylko
  minutę zaczynającą się dokładnie w tej chwili — po przerwie to minuta wznowienia.

Sygnał strategii (`strategies-tools`) się nie zmienia: o 22:00–22:04 okno silnika kończy się na 22:00 i ta świeca
po uzupełnieniu jest w archiwum. Team 14 po wdrożeniu dostaje `wait_for_bar_seconds` 420.

## Capabilities

### New Capabilities

Brak.

### Modified Capabilities

- `teams-steps`: wymaganie przepisu `strategy_execute` — zlecenie dopiero po cenie rynku po świecy sygnałowej,
  dłuższy czas czekania.

## Impact

- `modules/workbench/teams/steps/catalogue.py`, `strategy_execute.py`, testy kroku.
- Kontrakt terminala bez zmian: katalog przepisów jest czytany z kodu, typ parametru się nie zmienia.
- Bez migracji, ustawień i sekretów. Narzędzie `get_last_price` jest już w narzędziach przepisu.
- Ryzyko szczątkowe: gdy kolektor uzupełni świecę przed przerwą dopiero po 22:05, okno silnika przesuwa się na 22:05,
  sygnał odmawia do 22:10, a potem silnik trzyma już pozycję — krok kończy się wtedy pominięciem, jak dziś. Szybsze
  domykanie świecy przed przerwą w bramce to osobna zmiana.
- `design.md` i `tasks.md` pominięte: jedna decyzja (czekać na cenę, a nie na flagę `tradeable`, która jest
  buforowana minutę i nie mówi, czy rynek już notuje) mieści się w tym akapicie; zadania to kod i testy z tej listy.
