## Why

Zegar zespołów liczy każdy harmonogram w `Europe/Warsaw`. Zespół, który gra sesję nowojorską (wejście po
pierwszej świecy M5, 9:35 ET; wyjście 15:55 ET), dostaje wtedy złą godzinę przez kilka tygodni w roku, bo USA
i Europa zmieniają czas w różne niedziele — w marcu i od ostatniej niedzieli października do pierwszej
listopada otwarcie NY wypada godzinę wcześniej czasu polskiego. Operator musiałby poprawiać harmonogram cztery
razy w roku, a to dokładnie ten błąd, który strefa `Europe/Warsaw` miała usunąć.

## What Changes

- Harmonogram niesie **własną strefę** (nazwa IANA, np. `America/New_York`), domyślnie `Europe/Warsaw` — każdy
  istniejący harmonogram zachowuje się jak dotąd. Nieznana nazwa strefy jest odmową przy zapisie.
- Wyrażenie cron, dni tygodnia i podgląd najbliższych wyzwoleń są czytane w strefie harmonogramu; publikowane
  momenty zostają w UTC.
- Kontrakt teams: `ScheduleIn`, `NextFiresIn` i `ScheduleOut` dostają pole `timezone` (opcjonalne na wejściu).
  Kontrakt terminala regenerowany.
- Terminal: kreator harmonogramu wybiera strefę (Warszawa, Nowy Jork, Londyn, UTC); lista harmonogramów pokazuje
  strefę, gdy nie jest polska. Godziny najbliższych wyzwoleń terminal dalej pokazuje po polsku.
- Narzędzia rozmowy `schedule_team` / `edit_schedule` przyjmują `timezone`.

`review.md` pominięty: zmiana jest mała i nie dotyka ścieżki zleceń ani autoryzacji.

## Capabilities

### New Capabilities

(brak)

### Modified Capabilities

- `teams-schedules`: wymaganie „Moduł ma jeden zegar i sam publikuje najbliższe wyzwolenia” — strefa przestaje
  być stałą modułu i staje się własnością harmonogramu, z `Europe/Warsaw` jako domyślną.

## Impact

- `modules/workbench/teams`: migracja 0011 (kolumna `schedules.timezone`), `scheduler/timing.py`,
  `scheduler/clock.py`, `store/schedules.py`, `store/recurring.py`, `contract.py`, `routers/schedules.py`.
- `modules/workbench/teams_tools/tools/schedules.py` — parametr i opisy.
- `modules/terminal` — wygenerowany kontrakt teams, `ScheduleWizardDialog`, `SchedulesPanel`.
- Bez zmian: granica dobowa kosztu (nadal od północy UTC), wyzwalacze (interwał, nie cron).
