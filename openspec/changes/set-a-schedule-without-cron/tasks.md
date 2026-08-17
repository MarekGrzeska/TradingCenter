## 1. teams: strefa polska w zegarze

- [x] 1.1 `scheduler/timing.py` (nowy): stała `SCHEDULE_TIMEZONE = ZoneInfo("Europe/Warsaw")`
      i `fires_after`/`next_fire_after`, wyeksportowane z pakietu `scheduler`; `tzdata`
      dopisane do zależności modułu
- [x] 1.2 `_next_fire_and_skipped`: `croniter` startuje od `now`/`due_at` przeliczonych na
      `SCHEDULE_TIMEZONE`, wynik wraca do UTC przed zapisem
- [x] 1.3 `routers/schedules.py::_first_fire_at` i `next_fires`: ta sama zamiana strefy,
      jedna funkcja pomocnicza dla wszystkich trzech miejsc
- [x] 1.4 Testy zegara: harmonogram codzienny o 9:00 wyzwala się o 07:00 UTC w czasie letnim
      i 08:00 UTC w zimowym; harmonogram o 2:30 przechodzący obie noce zmiany czasu

## 2. teams: rytm na kontrakcie

- [x] 2.1 `teams/recurrence.py` (nowy — poza pakietem `scheduler`, bo czyta go `contract.py`): model `Recurrence` (`kind`, `minutes`, `hour`,
      `minute`, `weekdays`, `day_of_month`), `to_cron(recurrence)` i `from_cron(expression)`
      zwracające `None` dla wyrażenia spoza rytmów
- [x] 2.2 `contract.py`: `ScheduleIn` przyjmuje `recurrence` albo `cron_expression`, dokładnie
      jedno — walidator obok `_revision_selection_is_coherent`
- [x] 2.3 `contract.py`: `ScheduleOut.recurrence` wyliczane przez `from_cron` w `from_row`
- [x] 2.4 `routers/schedules.py`: `create_schedule` i `update_schedule` zamieniają
      `recurrence` na wyrażenie przed zapisem
- [x] 2.5 `POST /schedules/next-fires` — ciało jak `ScheduleIn` w części czasowej,
      odpowiedź `NextFiresOut`, ten sam limit `_MAX_NEXT_FIRES`, bez zapisu
- [x] 2.6 Testy tras: zapis rytmem, zapis wyrażeniem, oba naraz jako odmowa, żadne jako
      odmowa; podgląd dla szkicu; podgląd dla opisu niepoprawnego jako 422
- [x] 2.7 Testy `recurrence`: każdy rytm w obie strony, wyrażenie spoza rytmów jako `None`
- [x] 2.8 `README.md` modułu: strefa harmonogramów i to, co robi ze zmianą czasu
- [x] 2.9 `uv run ruff check .` · `uv run pyright` · `uv run pytest` · `uv run pytest -m db`

## 3. teams-mcp: snapshot kontraktu

- [x] 3.1 Odświeżyć `contract/teams.openapi.json`, potem
      `uv run python scripts/contract.py check`
- [x] 3.2 `tools/schedules.py`: narzędzie zostaje przy wyrażeniu, a jego opis i `describes`
      mówią, że wyrażenie znaczy czas polski, a `next_fire_at` jest w UTC
- [x] 3.3 `uv run ruff check .` · `uv run pyright` · `uv run pytest`

## 4. terminal: kreator harmonogramu

- [x] 4.1 `pnpm contract:generate` po zmianie `teams/contract.py`
- [x] 4.2 `teamsApi.ts`: `recurrence` w `Schedule` i `ScheduleDraft`, `previewNextFires(draft)`
      na `POST /schedules/next-fires`
- [x] 4.3 `scheduleDraft.ts`: szkic domyślny jako rytm „codziennie 9:00", przełączenie
      między rytmem a wyrażeniem bez gubienia drugiego
- [x] 4.4 `ScheduleWizardDialog.tsx` (nowy, na `ModalShell`): wybór rytmu, godzina, dni
      tygodnia jako chipy, dzień miesiąca, pola rewizji i potwierdzenia pracy bez nadzoru,
      zwijka „Zaawansowane" z wyrażeniem czasowym
- [x] 4.5 Podgląd w oknie: `previewNextFires` po każdej zmianie szkicu, z odłożeniem
      wywołania i anulowaniem poprzedniego
- [x] 4.6 `SchedulesPanel.tsx`: „New schedule" i „Edit" otwierają okno; wiersz listy opisuje
      harmonogram rytmem, a wyrażeniem tylko wtedy, gdy `recurrence` jest puste
- [x] 4.7 Czas na liście, w podglądzie i w historii wyzwoleń: czas polski z etykietą
      (`formatInstant`), czas przeglądarki obok tylko wtedy, gdy strefa przeglądarki jest
      inna (`formatBrowserInstant`); `formatUtcInstant` usunięte, bo nikt go już nie czyta
- [x] 4.8 Testy: zapis rytmem woła moduł z `recurrence`, harmonogram spoza rytmów otwiera się
      na wyrażeniu i zapisuje się bez zmiany, podgląd pochodzi z odpowiedzi modułu,
      odmowa modułu pokazana jego słowami

## 5. terminal: „Uruchom teraz" w widoku przebiegów

- [x] 5.1 `TeamRunsView.tsx`: przycisk w nagłówku, `ConfirmDialog` nazywający najnowszą
      rewizję (`api.latestRevision`)
- [x] 5.2 Po starcie: nowy przebieg jako oglądany i przeładowanie listy
- [x] 5.3 Odmowa modułu pokazana jego słowami, oglądany przebieg bez zmiany
- [x] 5.4 Testy: potwierdzenie uruchamia, zamknięcie okna nie uruchamia, odmowa widoczna
- [x] 5.5 `pnpm lint` · `pnpm typecheck` · `pnpm contract:check` · `pnpm test`

## 6. Domknięcie

- [x] 6.1 `openspec validate set-a-schedule-without-cron --strict`
- [x] 6.2 `review.md`
