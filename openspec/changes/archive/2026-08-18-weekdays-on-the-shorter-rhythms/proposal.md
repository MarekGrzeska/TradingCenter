## Why

Rytm „co godzinę" i „co N minut" nie ma dni tygodnia, więc harmonogram ułożony w kreatorze
budzi zespół także w sobotę i w niedzielę — a rynek, o który ten zespół pyta, stoi. Operator
ustawił na produkcji `35 * * * *` w przekonaniu, że opisuje dzień handlowy, i dostał dwa
dni przebiegów płaconych modelowi za odpowiedź „rynek zamknięty".

Dni tygodnia w rytmach są, ale wyłącznie przy `weekly`, czyli razem z jedną godziną doby.
„Poniedziałek–piątek" i „co godzinę" są dziś rozłączne: można mieć jedno albo drugie.
Kto chce obu, musi zejść do pola z pięcioma gwiazdkami — a to jest dokładnie ta droga, o
której `terminal-teams-schedules` mówi, że kreator ma jej operatorowi oszczędzić.

## What Changes

- `Recurrence` przyjmuje `weekdays` jako pole **opcjonalne** przy `every_minutes` i
  `hourly`, obok dotychczasowego obowiązkowego przy `weekly`. Brak pola znaczy dokładnie to,
  co dziś: siedem dni w tygodniu.
- `to_cron` wstawia te dni w piąte pole (`*/15 * * * 1,2,3,4,5`), `from_cron` czyta je z
  powrotem. Round-trip zostaje dowodem poprawności, tak jak jest.
- Komplet siedmiu dni MUST normalizować się do braku filtra, zanim cokolwiek zostanie
  zapisane — inaczej to samo wyzwolenie ma dwa zapisy i `from_cron` przestaje mieć jedną
  odpowiedź.
- **`daily` dni tygodnia nie dostaje.** `daily` z dniami tygodnia to jest `weekly`, co do
  wyrażenia; dwa rytmy dające jedno wyrażenie zabrałyby `from_cron` jednoznaczność, na
  której stoi cała para.
- Kreator harmonogramu pokazuje przełączniki dni przy tych dwóch rytmach — te same, które
  ma już `weekly`, nie drugi wynalazek obok nich.
- Bez zmian dla harmonogramów już zapisanych: `35 * * * *` dalej znaczy siedem dni i dalej
  wraca z kreatora jako ten sam rytm.

## Capabilities

### New Capabilities

Żadnych.

### Modified Capabilities

- `teams-schedules`: wymaganie „Harmonogram da się opisać rytmem, a moduł zna oba zapisy"
  — rytm krótszy niż dobowy może nieść dni tygodnia, a komplet dni jest tym samym, co ich
  brak.
- `terminal-teams-schedules`: wymaganie „Harmonogram układa się rytmem i godziną, nie
  wyrażeniem czasowym" — wybór dni przestaje być związany z jednym rytmem.

Oba wymagania żyją dziś w delcie niezarchiwizowanej zmiany `set-a-schedule-without-cron`,
a nie w `openspec/specs/`. Delta tej zmiany stoi na nich tak, jak tamta stanęła na delcie
`add-teams-schedules-and-triggers` — kolejność archiwizacji jest wtedy częścią roboty, nie
szczegółem.

## Impact

- `modules/teams`: `recurrence.py` (model, `to_cron`, `from_cron`, normalizacja),
  `contract.py` — czyli **kontrakt między modułami**, bo `Recurrence` jedzie w `ScheduleIn`
  i `ScheduleOut`.
- `modules/terminal`: `pnpm contract:generate` przepisuje `contract.teams.generated.ts`;
  `scheduleDraft.ts` i `ScheduleWizardDialog.tsx` dostają przełączniki dni przy dwóch
  rytmach; `SchedulesPanel.tsx` pokazuje je w opisie harmonogramu.
- Bez migracji: harmonogram trzyma w bazie wyrażenie czasowe, a rytm jest z niego
  wyliczany przy odczycie.
- Bez zmian w `scheduler/` — zegar dostaje wyrażenie i o rytmach nie wie.

## Zamknięcie

Zarchiwizowana 18 sierpnia 2026 z jednym niezaznaczonym polem, świadomie:

- **4.5** — „przestawić istniejący harmonogram `35 * * * *` na dni handlowe" — to czynność
  operatora na produkcji, a nie praca do wykonania w repozytorium. Kod, który na to
  pozwala, jest wdrożony i pokryty testami; kiedy operator z tego skorzysta, jest jego
  decyzją i nie jest warunkiem domknięcia zmiany.

`review.md` jest na miejscu i zostaje.
