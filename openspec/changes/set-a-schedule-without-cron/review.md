## Verdict

Poszło wszystko, co proponowano: harmonogram układa się rytmem w oknie modalnym z podglądem
liczonym przez moduł, wyrażenie cron zostało jako droga wyjścia pod „Advanced", czas
wyzwolenia jest liczony w `Europe/Warsaw` (publikowany dalej w UTC), a widok przebiegów
zespołu ma „Run now" z potwierdzeniem nazywającym rewizję. Strefa jest stałą modułu, nie
kolumną — tak, jak ustalono; migracji bazy nie było i nie potrzeba jej było.

**Nie do wzięcia za przeoczenie.** Po pierwsze: zapisane `next_fire_at` sprzed wdrożenia
zostaje nietknięte, więc pierwsze wyzwolenie po wdrożeniu wypada tam, gdzie wypadałoby
przedtem, a dopiero kolejne są liczone po polsku (design.md, Migration Plan). Po drugie:
granica dobowa kosztu nadal resetuje się o północy UTC — odstęp między resetem a porannym
wyzwoleniem pełza o godzinę dwa razy w roku, i to jest cena, którą wymaganie „Moduł ma jeden
zegar" nazywa wprost. Po trzecie: `tzdata` doszło do zależności `teams`, bo ani Windows, ani
szczupły obraz kontenera nie niosą bazy IANA — bez tego moduł nie wstaje, i tak właśnie
zachował się przy pierwszym uruchomieniu testów.

## Verified

W kolejności, w jakiej były uruchamiane:

| Gdzie | Komenda | Wynik |
|---|---|---|
| teams | `uv run ruff check .` · `uv run pyright` | `All checks passed!` · `0 errors, 0 warnings` |
| teams | `uv run pytest -q` | **389 passed** |
| teams | `uv run pytest -m db -q` | **170 passed, 219 deselected** |
| teams-mcp | `uv run python scripts/contract.py generate` → `check` | `Contract is up to date.` |
| teams-mcp | `uv run ruff check .` · `uv run pyright` · `uv run pytest -q` | `All checks passed!` · `0 errors` · **82 passed** |
| terminal | `pnpm contract:generate` | przepisany `contract.teams.generated.ts` |
| terminal | `pnpm typecheck` · `pnpm lint` · `pnpm contract:check` | bez wyjścia · bez wyjścia · `Every contract is up to date.` |
| terminal | `pnpm test` | **896 passed (57 plików)** |

Nie uruchamiano: `-m live --run-live` ani `--run-live-trading` (żaden nie dotyczy tej
zmiany), i nie uruchamiano całego stosu — zegar nie był oglądany, jak wyzwala naprawdę,
bo `SCHEDULER_ENABLED` jest w produkcji wyłączone i dowodem pozostają testy zegara.

## Findings

| Severity | Where | Finding | Status |
|---|---|---|---|
| poważne | `teams/scheduler/timing.py:22` | `ZoneInfo("Europe/Warsaw")` wywala moduł przy imporcie na maszynie bez bazy IANA — na Windowsie każdy test padał na `ZoneInfoNotFoundError`, a szczupły obraz kontenera zachowałby się tak samo w produkcji, przy starcie. | **FIXED** — `tzdata` w `pyproject.toml` z komentarzem mówiącym dlaczego |
| drobne | `teams/recurrence.py:104` | `from_cron` mogłoby „zaokrąglić" cudze wyrażenie do najbliższego rytmu (np. `0 9 * * 1,0` do poniedziałku i niedzieli w innej kolejności), a zapis oddałby operatorowi coś innego, niż wpisał. | zamknięte projektem: kandydat jest przyjmowany tylko wtedy, gdy `to_cron(kandydat)` jest znów tym samym napisem — `test_an_expression_outside_the_rhythms_is_no_rhythm` trzyma to na sześciu kształtach |
| drobne | `ScheduleWizardDialog.tsx:283` | Odjęcie ostatniego dnia tygodnia dałoby rytm, którego moduł odmawia — odmowa przyszłaby dopiero przy zapisie, przy formularzu wyglądającym na gotowy. | zamknięte projektem: `toggle` nie pozwala zdjąć ostatniego dnia |
| do wiedzy | `teams/routers/schedules.py:262` | `POST /schedules/next-fires` nie sprawdza właściciela poza tym, że ktoś jest zalogowany — nie dotyka żadnego wiersza i odpowiada o cudzym niczym, ale jest to jedyna trasa harmonogramów bez filtra właściciela. Świadome, opisane w docstringu. | otwarte, świadome |
| do wiedzy | `terminal/src/ui/formatTime.ts` | `formatUtcInstant` usunięte razem z ostatnim czytelnikiem (panel harmonogramów i historia wyzwoleń). Kto szuka UTC w terminalu, nie znajdzie go już nigdzie — to jest właśnie zmiana wymagania „Czas jest pokazany tak, żeby nie trzeba było go przeliczać". | otwarte, świadome |

## Spec coverage

| Requirement / Scenario | Proven by |
|---|---|
| **teams-schedules** — Harmonogram da się opisać rytmem, a moduł zna oba zapisy | |
| Harmonogram zapisany rytmem | `teams/tests/test_schedules_routes.py::test_a_schedule_saved_as_a_rhythm_comes_back_as_the_same_rhythm`; `teams/tests/test_recurrence.py::test_a_rhythm_becomes_its_expression` |
| Wyrażenie spoza rytmów kreatora | `teams/tests/test_schedules_routes.py::test_a_schedule_saved_as_an_expression_outside_the_rhythms_carries_no_rhythm`; `teams/tests/test_recurrence.py::test_an_expression_outside_the_rhythms_is_no_rhythm` |
| **teams-schedules** — Moduł liczy najbliższe wyzwolenia także dla opisu, którego nie zapisano | |
| Podgląd przed zapisem | `teams/tests/test_schedules_routes.py::test_next_fires_are_previewed_for_a_draft_nobody_saved` |
| Opis, którego nie da się wykonać | `teams/tests/test_schedules_routes.py::test_a_draft_that_cannot_be_run_is_refused_rather_than_previewed`; `::test_a_schedule_must_name_its_timing_exactly_once` |
| **teams-schedules** — Moduł ma jeden zegar i sam publikuje najbliższe wyzwolenia (MODIFIED) | |
| Operator pyta o najbliższe wyzwolenia | `teams/tests/test_schedules_routes.py::test_next_fires_preview_returns_the_requested_count_in_order` |
| Zmiana czasu | `teams/tests/test_schedule_timing.py::test_the_clock_change_moves_utc_and_leaves_the_wall_clock_alone`; `::test_nine_in_the_morning_is_nine_in_poland_in_summer`; `::test_nine_in_the_morning_is_nine_in_poland_in_winter` |
| Budzenie wyłączone ustawieniem | `teams/tests/test_scheduler_clock.py::test_a_disabled_clock_never_starts_a_background_task` (bez zmian tą zmianą) |
| **terminal-teams-schedules** — Harmonogram układa się rytmem i godziną, nie wyrażeniem czasowym | |
| Harmonogram codzienny | `terminal/src/teams/SchedulesPanel.test.tsx::posts a rhythm the operator chose, with no cron expression typed anywhere` |
| Rytm spoza kreatora | `terminal/src/teams/SchedulesPanel.test.tsx::opens a schedule the wizard has no rhythm for on its own expression, and saves it unchanged` |
| **terminal-teams-schedules** — Operator widzi skutek harmonogramu przed zapisaniem go | |
| Podgląd w trakcie układania | `terminal/src/teams/SchedulesPanel.test.tsx::asks the module again when the operator changes the time, before anything is saved` |
| **terminal-teams-schedules** — Terminal nie liczy czasu wyzwolenia sam (MODIFIED) | |
| Podgląd najbliższych wyzwoleń | `terminal/src/teams/SchedulesPanel.test.tsx::previews a draft's next fires from the module, not from a local parser` (czasy spoza siatki jakiegokolwiek rytmu) |
| Rytm zamieniany na wyrażenie czasowe | `terminal/src/teams/teamsApi.test.ts::posts a rhythm in the module's own spelling, snake_case and all` — patrz też Gaps |
| **terminal-teams-schedules** — Czas jest pokazany tak, żeby nie trzeba było go przeliczać (MODIFIED) | |
| Operator w strefie polskiej | `terminal/src/teams/SchedulesPanel.test.tsx::shows the module's own timestamp in Polish time — never recomputed` |
| Operator w innej strefie | `terminal/src/teams/SchedulesPanel.test.tsx::shows the browser's own zone beside Polish time for an operator outside Poland` |
| **terminal-teams** — Przebieg da się uruchomić z widoku przebiegów zespołu | |
| Uruchomienie z listy przebiegów | `terminal/src/teams/TeamsView.test.tsx::starts a run from here, once the question naming the revision is answered` |
| Uruchomienie odrzucone przez moduł | `terminal/src/teams/TeamsView.test.tsx::keeps the refusal beside the question, in the module's own words` |
| Rezygnacja z uruchomienia | `terminal/src/teams/TeamsView.test.tsx::starts nothing when the question is dismissed` |

## Gaps

- **„Rytm zamieniany na wyrażenie czasowe" jest dowiedziony pozytywnie, nie negatywnie.**
  Test pokazuje, że terminal wysyła `recurrence` i że zamiany dokonuje moduł; nie ma
  strażnika, który by upadł, gdyby ktoś kiedyś dopisał w terminalu własne składanie
  wyrażenia z pól. `pickersComeFromTheModule.test.ts` jest miejscem, gdzie taki strażnik
  by mieszkał, gdyby powstał — nie powstał tą zmianą.
- **Zegar nie był oglądany na żywym stosie.** Wyzwolenie o polskiej godzinie jest
  dowiedzione testami `croniter` + strefa, nie przebiegiem, który naprawdę ruszył o 9:00 —
  `SCHEDULER_ENABLED` jest w produkcji wyłączone i włącza je operator.
- **Noc przejścia na czas letni jest utrwalona, nie rozstrzygnięta.**
  `test_a_schedule_inside_the_spring_gap_still_fires_that_day` zapisuje, co `croniter` robi
  z godziną, której nie ma (harmonogram nie znika na ten dzień), a nie co „powinien" robić.
  To świadomie: wybór biblioteki jest tu zachowaniem, nie wymaganiem.
