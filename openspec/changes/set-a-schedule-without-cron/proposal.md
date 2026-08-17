## Why

Harmonogram zespołu układa się dziś przez wpisanie wyrażenia cron w pole tekstowe, a moduł
czyta to wyrażenie w UTC. Operator, który nie zna crona, nie ma jak zapisać „codziennie
o 9:00", a operator, który go zna, i tak wpisuje 7:00 latem i 8:00 zimą, żeby zespół ruszył
o dziewiątej rano w Polsce — zmiana czasu przesuwa mu harmonogram dwa razy w roku i nic o tym
nie mówi. Do tego przebieg da się uruchomić ręcznie tylko z katalogu: operator, który patrzy
na listę przebiegów i chce zobaczyć, co zespół powie teraz, musi wyjść z tego widoku.

## What Changes

- Harmonogram jest opisywany rytmem, godziną i dniami zamiast wyrażeniem cron: co N minut,
  co godzinę, codziennie, w wybrane dni tygodnia, w wybrany dzień miesiąca. Wyrażenie cron
  zostaje jako zapis pod spodem i jako droga wyjścia dla rytmu, którego kreator nie obejmuje.
- Terminal układa harmonogram w oknie modalnym z żywym podglądem najbliższych wyzwoleń,
  liczonym przez moduł dla jeszcze niezapisanego szkicu — dziś moduł odpowiada tylko dla
  harmonogramu już zapisanego.
- **BREAKING** Czas wyzwolenia jest liczony w strefie `Europe/Warsaw`, nie w UTC.
  Harmonogram zapisany dotąd jako „9:00" wyzwoli się o 9:00 czasu polskiego, czyli o dwie
  godziny wcześniej w UTC niż dotąd. Na drucie moment wyzwolenia pozostaje w UTC.
- Widok przebiegów zespołu dostaje „Uruchom teraz" z potwierdzeniem nazywającym rewizję,
  którą uruchomi.

## Capabilities

### New Capabilities

Brak — wszystkie trzy zdolności, których to dotyczy, już istnieją.

### Modified Capabilities

- `teams-schedules`: czas wyzwolenia liczony w strefie polskiej zamiast w UTC (zmiana czasu
  nie przesuwa godziny harmonogramu); moduł publikuje najbliższe wyzwolenia także dla opisu
  harmonogramu, który nie został jeszcze zapisany.
- `terminal-teams-schedules`: harmonogram układany rytmem i godziną, nie wyrażeniem cron;
  czas pokazany w strefie polskiej zamiast w UTC obok czasu przeglądarki.
- `terminal-teams`: przebieg da się uruchomić z widoku przebiegów zespołu, nie tylko
  z katalogu.

## Impact

- `modules/teams` — `contract.py` (`ScheduleIn`/`ScheduleOut`, nowe `NextFiresIn`),
  `routers/schedules.py`, `scheduler/clock.py`. Kontrakt między modułami, więc także
  snapshot `teams-mcp/contract/teams.openapi.json` i zadanie CI tego modułu.
- `modules/terminal` — `SchedulesPanel.tsx` i nowy kreator, `scheduleDraft.ts`,
  `teamsApi.ts`, `TeamRunsView.tsx`, wygenerowany `contract.teams.generated.ts`
  (`pnpm contract:generate`).
- Bez migracji: strefa jest stałą modułu, nie kolumną. Istniejące wiersze `schedules`
  zachowują swoje wyrażenia cron i zmieniają moment wyzwolenia — patrz Migration Plan
  w `design.md`.
- Granica dobowa kosztu nadal liczy się od północy UTC, więc odstęp między resetem budżetu
  a porannym wyzwoleniem zmienia się przy zmianie czasu o godzinę.
