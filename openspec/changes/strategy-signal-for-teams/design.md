## Context

Silnik (`strategies/engine.py`, `simulate`) decyduje na zamknięciu każdej świecy interwału strategii i wypełnia od
następnej minuty. Po pętli to, co ostatnia decyzja zostawiła w toku — zlecenie wejścia, pozycja z `exit_at_next_minute`
— jest rozliczane do końca zakresu, a otwarta pozycja zamykana jako `end_of_range`. Dane czyta `reading.read` z
archiwum `/market` w tym procesie, z rozgrzewką wyliczoną z dokumentu (`requirements.needs`).

## Goals / Non-Goals

**Non-Goals:** rozliczanie z prawdziwą pozycją na koncie (to robi zespół, porównując sygnał z `get_positions`);
wielkość w jednostkach; sygnał bez wskazanej rewizji; harmonogram, który woła sygnał sam (to harmonogram zespołu).

## Decisions

**D1. Sygnał to `simulate`, zatrzymany przed rozliczeniem tego, co w toku — nie druga funkcja „decide”.** `Result`
dostaje pole `in_flight`: stan zlecenia i pozycji zaraz po ostatniej decyzji, zanim cokolwiek zostanie rozliczone do
końca zakresu. Druga, „lżejsza” funkcja oceniająca warunki na ostatniej świecy powtórzyłaby kolejność silnika
(najpierw pozycja i jej wyjścia, potem blokady, potem wejścia po kolei, `daily_stop_r`, `trades_today`) i rozjechałaby
się z nim przy pierwszej zmianie. Transakcje się nie zmieniają, więc `ENGINE_VERSION` zostaje.

**D2. Okno: stała liczba świec decyzji wstecz od ostatniej zamkniętej, plus rozgrzewka dokumentu.** 2 000 świec
(M5: ok. tydzień handlu), obcięte do `STRATEGIES_MAX_EXECUTION_BARS` serii wykonania. Silnik zaczyna okno bez pozycji,
więc pozycja otwarta przed jego początkiem jest niewidoczna — dla strategii, która trzyma krócej niż okno, to nic; dla
innej sygnał mówi „trzymaj” dopiero od pozycji otwartej w oknie. Odpowiedź podaje początek okna, żeby to było widać.
Alternatywa — liczyć od początku archiwum — kosztowałaby lata minut na każde wywołanie.

**D3. Koszty: zapisany profil instrumentu, a bez niego zera; depozyt: zapisany, bez niego odmowa.** Sygnał niczego nie
zapisuje, więc nie pyta brokera (to zapisuje profil i depozyt). Koszty nie zmieniają decyzji wejścia i wyjścia, tylko
R i kapitał w oknie; odpowiedź mówi, które koszty wzięto. Depozyt jest potrzebny `simulate` dla `margin_fraction`;
strategia z backtestem już go ma, a bez niego odmowa każe najpierw uruchomić backtest.

**D4. Liczone w wątku, z limitem czasu — nie w procesie kolejki.** Okno jest małe (ułamek sekundy dla M5), a proces
kolejki istnieje dla runów liczonych minutami. Wątek nie blokuje pętli; limit czasu chroni przebieg zespołu.

**D5. Dwa serwery FastMCP z jednego `register`.** Pełny — dla rozmowy, jak dziś, plus `strategy_signal`. Czytający —
dla zespołów, tylko `list_strategies`, `read_strategy` i `strategy_signal`. Te same funkcje narzędzi, ta sama logika;
który serwer co ma, decyduje lista nazw w `mcp_app.py`, a test czyta ją z ogłoszonych narzędzi.

## Risks / Trade-offs

- [Sygnał wołany przed zamknięciem świecy dostaje decyzję z poprzedniej] → odpowiedź podaje moment świecy i jej wiek;
  opis narzędzia każe go sprawdzić. Harmonogram 9:35 ET odpala po zamknięciu świecy 9:30–9:35.
- [Archiwum spóźnia ostatnią świecę o kilka sekund] → brak świecy jest odmową nazywającą lukę (spec); zespół może
  powtórzyć wywołanie.
- [Zespół pomyli „trzymaj” silnika z pozycją na koncie] → odpowiedź nazywa to pozycją silnika w oknie, z jej czasem
  wejścia; porównanie z kontem jest zadaniem zespołu.

## Migration Plan

Bez migracji. Rejestr zespołów dostaje trzy narzędzia przy starcie procesu, gdy pakiet jest zamontowany; istniejące
rewizje zespołów nie zmieniają się.
