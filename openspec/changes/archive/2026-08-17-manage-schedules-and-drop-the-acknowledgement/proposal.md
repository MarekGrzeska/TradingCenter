## Why

Harmonogram da się dziś **założyć** i nic poza tym: `teams-mcp` publikuje trzy narzędzia,
z których jedno zakłada harmonogram, drugie wyzwalacz, trzecie czyta listę. Zatrzymania,
poprawki ani usunięcia nie ma w czacie wcale, a w terminalu jest samo „Disable" —
**usunięcia nie ma nigdzie w całej platformie**, bo `teams` nie ma na to trasy. Katalog
harmonogramów tylko rośnie.

Drugą połową jest zgoda na pracę bez nadzoru, która zatrzymała operatora dwa razy w jednej
sesji i za każdym razem kazała mu szukać przełącznika, którego nie ma. Powód, dla którego
znika, nie jest wygodą: **to zabezpieczenie jest wołane w jednym miejscu z dwóch.**
`check_unattended` chodzi wyłącznie przy zapisie harmonogramu; ścieżka wyzwolenia
(`scheduler/clock.py` → `runner/`) nie pyta o nie ani razu, a przy trybie „najnowsza
rewizja" bierze rewizję z chwili wyzwolenia. Harmonogram zapisany legalnie nad zespołem bez
narzędzi zapisujących chodzi więc dalej sam po tym, jak operator doda do zespołu
`place_order` — bez żadnego potwierdzenia i bez pytania. Zabezpieczenie, które zatrzymuje
uczciwą drogę i przepuszcza tę drugą, uczy klikania w checkbox i niczego nie chroni.

Co zostaje, i to działa naprawdę: konto demonstracyjne wymuszone u gatewaya, granice
handlowe zapisane w rewizji, dobowa granica kosztu zespołu i wiersz śladu przed każdym
zleceniem.

## What Changes

- **`unattended_ack` znika w całości** — z kontraktu (`ScheduleIn`/`ScheduleOut`,
  `TriggerIn`/`TriggerOut`), z bazy przez migrację, z `validation.check_unattended` i z
  kreatora w terminalu. Wymaganie, które go żądało, zostaje **wycofane**, a nie obejrzone.
- **Harmonogram i wyzwalacz dają się usunąć.** Nowe trasy `DELETE /schedules/{id}` i
  `DELETE /triggers/{id}` w `teams`, narzędzie w `teams-mcp` i przycisk w terminalu obok
  dzisiejszego „Disable".
- **Usunięcie zabiera ze sobą historię wyzwoleń tego harmonogramu, ale nie przebiegi.**
  Wiersz historii wskazuje albo harmonogram, albo wyzwalacz — `CHECK` w `0005` nie
  dopuszcza żadnego innego stanu — więc osierocić go się nie da. Przebiegi zostają, bo to
  historia wskazuje na nie, a nie odwrotnie: koszt i ślad zleceń przeżywają usunięcie
  harmonogramu, który je zamówił.
- **Czat dostaje zarządzanie:** zatrzymanie, wznowienie, poprawkę i usunięcie, dla obu
  rodzajów. Trasy `PUT`, `enable` i `disable` już istnieją; brakuje ich w zestawie narzędzi.
- **BREAKING** dla odbiorcy kontraktu: `unattended_ack` przestaje być polem. Odbiorcą jest
  wyłącznie terminal tego repozytorium i zmienia się razem z modułem.

## Capabilities

### New Capabilities

Żadnych.

### Modified Capabilities

- `teams-schedules`: wymaganie „Harmonogram nad rewizją z narzędziami zapisującymi wymaga
  jawnego potwierdzenia" zostaje **usunięte**; dochodzi wymaganie o usuwaniu harmonogramu i
  wyzwalacza wraz z tym, co usunięcie zabiera, a czego nie rusza.
- `teams-mcp-tools`: zestaw narzędzi obejmuje zarządzanie harmonogramem, nie samo jego
  założenie.
- `teams-mcp-authorship`: wymaganie „Moduł nie rozszerza uprawnień, które operator już ma"
  wylicza dziś wśród odmów „brak potwierdzenia pracy bez nadzoru" — odmowa, której już nie
  będzie.
- `terminal-teams-schedules`: znika pole zgody z formularza, dochodzi usuwanie z listy.

Wszystkie cztery żyją dziś w deltach niezarchiwizowanych zmian (`add-teams-schedules-and-triggers`,
`add-teams-mcp`, `set-a-schedule-without-cron`, `weekdays-on-the-shorter-rhythms`), nie w
`openspec/specs/`. Kolejność archiwizacji jest częścią roboty i jest opisana w `design.md`.

## Impact

- `modules/teams`: `contract.py`, `validation.py`, `routers/schedules.py`, `store.py`,
  migracja kasująca kolumnę i dodająca kasowanie kaskadowe historii.
- `modules/teams-mcp`: nowe narzędzia nad istniejącymi trasami plus usuwanie; snapshot
  `contract/teams.openapi.json` do przegenerowania.
- `modules/terminal`: `pnpm contract:generate`, `teamsApi.ts`, `scheduleDraft.ts`,
  `ScheduleWizardDialog.tsx`, `SchedulesPanel.tsx`.
- Bez zmian w `scheduler/` — zegar nie czytał tego pola i nie zyskuje nic do usuwania.
- Produkcja: harmonogramy zapisane z `unattended_ack = true` działają dalej; kolumna znika,
  a nie jej znaczenie.
