## 1. Workbench: dane i zegar

- [x] 1.1 Migracja teams 0011: `schedules.timezone text NOT NULL DEFAULT 'Europe/Warsaw'`
- [x] 1.2 `scheduler/timing.py`: `fires_after` / `next_fire_after` przyjmują strefę (domyślnie `Europe/Warsaw`); testy NY w tygodniu 26–30.10.2026 i dni tygodnia w strefie NY
- [x] 1.3 Store: kolumna w `SCHEDULE_COLUMNS`, INSERT i UPDATE
- [x] 1.4 Zegar: `_next_fire_and_skipped` liczy w strefie wiersza
- [x] 1.5 Kontrakt: `timezone` w `ScheduleTiming` (walidacja `ZoneInfo`, odmowa nazywa strefę) i w `ScheduleOut`; routery zapisu, edycji i podglądu przekazują ją do `timing`
- [x] 1.6 Testy tras: zapis z `America/New_York` publikuje `next_fire_at` w UTC wg NY; nieznana strefa → 422; zapis bez strefy → `Europe/Warsaw`

## 2. Narzędzia rozmowy

- [x] 2.1 `teams_tools/tools/schedules.py`: parametr `timezone` w `schedule_team` i `edit_schedule`, opisy bez „always Poland”, podsumowanie harmonogramu podaje strefę

## 3. Terminal

- [x] 3.1 `contract-sync`: regeneracja kontraktu teams w terminalu (i w pocket, jeśli go niesie)
- [x] 3.2 `ScheduleWizardDialog`: wybór strefy (Warszawa, Nowy Jork, Londyn, UTC; nieznana z zapisu zachowana), etykieta crona bez „Poland”
- [x] 3.3 `SchedulesPanel`: nazwa strefy obok rytmu, gdy nie jest polska; testy: happy path, odmowa nieznanej strefy

## 4. Domknięcie

- [x] 4.1 `openspec validate schedule-in-its-own-timezone --strict`; README workbench, jeśli wspomina stałą strefę
