## Why

Zespół, który ma grać zapisaną strategię na demo, dziś dostaje jej reguły tylko jako prozę w swoim prompcie i sam
odtwarza je z świec i wskaźników. To dwie implementacje tej samej reguły: silnik backtestu i model, który ją
interpretuje — i nic nie gwarantuje, że zdecydują tak samo (warunek równości, numer świecy sesji, EMA bez resetu, okno
wyjścia). Wynik backtestu przestaje wtedy mówić cokolwiek o tym, co zespół robi na koncie.

## What Changes

- Nowe narzędzie **`strategy_signal`**: dla strategii i jej **wskazanej** rewizji odtwarza silnik backtestu na oknie
  kończącym się ostatnią zamkniętą świecą i podaje, co silnik zrobiłby teraz — wejście (strona, typ zlecenia, cena),
  wyjście należne otwartej pozycji, albo nic — oraz moment świecy, z której to wynika, i jak dawno się zamknęła. Podaje
  też regułę wielkości z dokumentu (np. depozyt jako ułamek kapitału) — wielkość w jednostkach liczy zespół z
  prawdziwego salda przez `trading-mcp`, bo pakiet strategii dalej nie ma drogi do konta.
- Zespoły dostają **trzy narzędzia tylko do odczytu**: `list_strategies`, `read_strategy` i `strategy_signal`. Żadne
  narzędzie, które zapisuje rewizję, szkic albo uruchamia lub usuwa backtest, nie trafia do zespołów — powód dotychczasowej
  reguły (harmonogram zużywający kolejkę i licznik prób) zostaje w mocy, bo sygnał nie jest uruchomieniem i nie liczy się
  jako próba.
- Rozmowa też dostaje `strategy_signal` — operator może zapytać „co strategia zrobiłaby teraz” bez zespołu.
- **Reguła architektoniczna:** „narzędzia strategii należą tylko do rozmowy” (CLAUDE.md, README pakietu, spec
  `strategies-tools`) zmienia się na „narzędzia zapisujące i uruchamiające należą tylko do rozmowy; trzy narzędzia do
  odczytu mają też zespoły”.

`review.md` będzie napisany: zmiana dotyka reguły nazwanej w CLAUDE.md i drogi, którą zespół podejmuje decyzję o
zleceniu.

## Capabilities

### New Capabilities

(brak)

### Modified Capabilities

- `strategies-tools`: powierzchnia narzędzi zyskuje `strategy_signal`; wymaganie „Narzędzia strategii dostaje tylko
  rozmowa” zastąpione podziałem na narzędzia rozmowy i trzy narzędzia do odczytu dla zespołów; nowe wymaganie o tym, co
  `strategy_signal` odpowiada.

## Impact

- `modules/workbench/strategies`: `engine.py` (wynik symulacji niesie to, co zostało w toku po ostatniej decyzji),
  nowy moduł sygnału, `tools/`, `mcp_app.py` (drugi, czytający serwer dla zespołów), README.
- `modules/workbench/workbench/app.py`: rejestr zespołów dostaje czytający serwer strategii, gdy pakiet jest zamontowany.
- `CLAUDE.md` — jedno zdanie w mapie (`modules/workbench`).
- Bez zmian: kontrakt REST pakietu i kontrakty terminala (narzędzie nie ma trasy), `ENGINE_VERSION` (wyniki backtestów się
  nie ruszają), droga do konta (dalej tylko `trading-mcp`).
- Koszt bazy: jeden odczyt świec i wskaźników okna na wywołanie; zespół woła to kilka razy dziennie (`db-cost-check`).
