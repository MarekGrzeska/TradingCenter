## 1. Rytm w module

- [x] 1.1 `recurrence.py`: `weekdays` jako pole opcjonalne dla `every_minutes` i `hourly`
      — rozdzielić `_FIELDS` na wymagane i dopuszczalne, tak żeby `daily` i `monthly`
      dalej odmawiały tego pola (D1)
- [x] 1.2 Normalizacja kompletu siedmiu dni do `None` w walidatorze `Recurrence` (D2)
- [x] 1.3 `to_cron`: dni w piątym polu dla obu nowych rytmów, listą po przecinku (D4)
- [x] 1.4 `from_cron`: `*/N * * * <dni>` i `<M> * * * <dni>` jako rytmy, przed gałęzią
      `weekly`; `weekly` dalej wymaga godziny, więc `<M> * * * <dni>` nie może w nią wpaść
- [x] 1.5 Testy `recurrence`: round-trip dla obu nowych rytmów, komplet dni znika,
      `daily` z dniami odmawia, pusta lista odmawia, `1-5` wpisane ręcznie zostaje bez rytmu

## 2. Kontrakt

- [x] 2.1 `teams/contract.py`: sprawdzić, że `ScheduleIn`/`ScheduleOut` niosą nowe pole bez
      zmiany kształtu (dziedziczą z `Recurrence`), i że odmowa z 1.1 wychodzi jako 422 z
      nazwą pola
- [x] 2.2 `uv run python -m teams.openapi` — schemat niesie `weekdays` przy rytmach
- [x] 2.3 Testy tras: zapis harmonogramu rytmem godzinowym z dniami, odczyt zwraca ten sam
      rytm; zapis rytmu dobowego z dniami odmawia
- [x] 2.4 Podgląd najbliższych wyzwoleń (`/schedules/preview` albo trasa, którą kreator
      pyta) respektuje dni tygodnia

## 3. Kreator w terminalu

- [x] 3.1 `pnpm contract:generate` — przepisany `contract.teams.generated.ts`
- [x] 3.2 `scheduleDraft.ts`: `weekdays` przenoszone przy zmianie rytmu między
      `every_minutes`, `hourly`, `weekly`; domyślnie brak dni przy dwóch pierwszych
- [x] 3.3 `scheduleDraft.ts`: opis rytmu po polsku dla rytmu z dniami (funkcja `describe`)
- [x] 3.4 `ScheduleWizardDialog.tsx`: przełączniki dni przy `every_minutes` i `hourly` —
      ta sama kontrolka co przy `weekly` (D5), niepokazywana przy `daily` i `monthly`
- [x] 3.5 Zapis zablokowany przy zerze zaznaczonych dni, z komunikatem
- [x] 3.6 Komplet siedmiu dni pokazany jako brak ograniczenia, nie jako siedem zaznaczeń
- [x] 3.7 `SchedulesPanel.tsx`: harmonogram z dniami opisany nimi na liście
- [x] 3.8 Testy terminala: weekend odznaczony przy rytmie godzinowym, podgląd bez soboty i
      niedzieli, brak wyboru dni przy `daily`, odmowa przy zerze dni

## 4. Domknięcie

- [x] 4.1 `modules/teams`: `uv run pytest`, `uv run pytest -m db`, `uv run ruff check .`,
      `uv run pyright`
- [x] 4.2 `modules/terminal`: `pnpm test`, `pnpm lint`, `pnpm typecheck`,
      `pnpm contract:check`
- [x] 4.3 `openspec validate weekdays-on-the-shorter-rhythms --strict`
- [x] 4.4 Wdrożenie w kolejności: `teams` przed terminalem (design, Risks)

      Kolejność wymusza się sama: `deploy-teams.yml` i `deploy-terminal.yml` startują
      z tego samego merge'a, a terminal sprzed zmiany nie wysyła dni, więc okno między
      nimi jest dotychczasowym zachowaniem, nie awarią.
- [ ] 4.5 Na produkcji: przestawić istniejący harmonogram `35 * * * *` na dni handlowe
      i sprawdzić, że w sobotę się nie wyzwala
- [x] 4.6 `review.md`
