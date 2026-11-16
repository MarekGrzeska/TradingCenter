## Why

16 listopada 2026 cztery wycofane zespoły (8, 11, 12, 13 — dwa z nich na koncie realnym) wystartowały z
harmonogramu, wysłały powiadomienia na Telegram, a zespół 12 złożył zlecenie na demo. Wycofanie stawiało tylko
`teams.archived_at`; harmonogramy i wyzwalacze zostawały włączone, a zegar wybiera je po `enabled` i
`next_fire_at`, nie pytając o zespół. Operator rozumie „Retire” jako „ten zespół już nic nie robi” — i tak MUST
być. Drugi brak: wycofany zespół znikał z terminala bez śladu i bez drogi powrotu, więc pomyłki nie dało się
cofnąć inaczej niż w bazie.

## What Changes

- Wycofanie zespołu wyłącza w tej samej transakcji wszystkie jego harmonogramy i wyzwalacze, z powodem
  „zespół wycofany z katalogu”.
- Zegar nie przejmuje wyzwolenia harmonogramu ani wyzwalacza wycofanego zespołu — druga linia, gdyby wiersz
  włączono inną drogą.
- `GET /teams?archived=true` — lista wycofanych zespołów z momentem wycofania (`archived_at`).
- `POST /teams/{id}/restore` — przywraca zespół do katalogu. Harmonogramy i wyzwalacze **zostają wyłączone**;
  operator włącza je sam, każdy osobno. Przywrócenie zespołu na koncie realnym nie może samo wznowić handlu.
- Terminal: w zakładce Teams przełącznik „Active / Retired”; widok wycofanych pokazuje nazwę, opis, rewizję,
  moment wycofania i przycisk „Restore”.

## Capabilities

### New Capabilities

Brak.

### Modified Capabilities

- `teams-catalogue`: wycofanie wyłącza harmonogramy i wyzwalacze; wycofany zespół da się wylistować i przywrócić.
- `teams-schedules`: zegar nie odpala harmonogramu ani wyzwalacza wycofanego zespołu.
- `terminal-teams`: widok wycofanych zespołów z przywróceniem.

## Impact

- `modules/workbench/teams/` (`store/catalogue.py`, `store/recurring.py`, `routers/catalogue.py`, `contract.py`),
  testy w `tests/teams/`.
- Kontrakt terminala: nowe pole `archived_at` w `TeamOut`, nowa trasa — regeneracja `contract.teams.generated.ts`.
- `modules/terminal/src/teams/` (`teamsApi.ts`, `TeamsView.tsx`, nowy `RetiredTeams.tsx`).
- Bez migracji: `archived_at` już istnieje. Dane produkcyjne poprawione ręcznie 16.11 (16 harmonogramów wyłączonych).
- `design.md` pominięty: jedyna decyzja — przywrócenie nie włącza harmonogramów — jest uzasadniona wyżej.
