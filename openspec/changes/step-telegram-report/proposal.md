## Why

Zespoły z krokiem `strategy_execute` (team 13, nowy zespół demo dla strategii 68) opowiadają wynik kroku na Telegram
przez agenta z modelem. Operator zgłasza, że w tych wiadomościach często brakuje ceny transakcji, a po zamknięciu
zysku i straty. Przyczyna jest po obu stronach: wynik kroku przy wyjściu nie niesie ani ceny wejścia, ani wyniku w
pieniądzach, więc agent nie ma czego podać, a gdy ma, model raz pole poda, raz pominie. Operator chce kroków
deterministycznych, gdzie to możliwe — także powiadomienia.

## What Changes

- `strategy_execute` przy wejściu zawsze podaje cenę wykonania: z potwierdzenia zlecenia, a gdy go brak, z ceny
  otwarcia pozycji na rachunku. Przy wyjściu podaje cenę otwarcia, cenę zamknięcia, wielkość, różnicę w punktach i
  wynik w walucie rachunku jako różnicę salda przed i po zamknięciu; gdy saldo się nie zmieni w krótkim oknie, podaje
  ostatni niezrealizowany wynik pozycji, oznaczony jako przybliżony.
- Nowy przepis `telegram_report`: krok bez modelu, który czyta wynik kroku poprzednika i wysyła jedną wiadomość o
  stałym kształcie przez `send_telegram_message` — przy wejściu, wyjściu, odmowie, wyniku nieznanym, strategii
  nieobsługiwanej i pominięciu z innego powodu niż wcześniejsza próba na tej świecy; przy braku działania milczy.
  Pole, którego wynik nie niesie, jest napisane jako „niedostępne”, nigdy szacowane.
- Krok dostaje wyniki poprzedników tak jak agent (dziś krok ich nie widział, bo pierwszy przepis ich nie potrzebował).

## Capabilities

### New Capabilities

Brak.

### Modified Capabilities

- `teams-steps`: dwa nowe wymagania — wynik `strategy_execute` niesie cenę i wynik transakcji; przepis `telegram_report`.

## Impact

- `modules/workbench/teams/steps/` (katalog, `strategy_execute.py`, nowy `telegram_report.py`, `runtime.py`),
  `teams/runner/engine.py` (krok dostaje `given`), testy, README pakietu.
- Kontrakt terminala: katalog przepisów jest czytany z kodu, typ parametru `text` już istnieje — bez zmiany kontraktu.
- Bez nowych ustawień, sekretów, migracji. Zespoły z agentem-reporterem działają dalej bez zmian.
- `design.md` pominięty: jedna decyzja (wynik z różnicy salda zamiast z potwierdzenia brokera, bo to drugie byłoby
  zmianą kontraktu bramy i migawki trading-mcp) mieści się w tym akapicie.
