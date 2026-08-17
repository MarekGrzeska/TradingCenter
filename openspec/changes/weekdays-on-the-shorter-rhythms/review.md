# Review

## Verdict

Rytm „co godzinę" i „co N minut" niosą teraz dni tygodnia, a operator wyłącza weekend dwoma
kliknięciami w tych samych przełącznikach, które ma rytm tygodniowy. Kształt na drucie się
nie zmienił ani o pole: `weekdays` już tam było jako `number[] | null`, więc cała zmiana
kontraktu to opis w schemacie — a to znaczy, że terminal sprzed niej i moduł po niej mijają
się bez awarii.

Rdzeniem nie są dni, tylko **jedna postać kanoniczna**: `from_cron` odpowiada rytmem tylko
wtedy, gdy `to_cron` z tego rytmu daje z powrotem to samo wyrażenie, więc każdy sposób
zapisania jednego wyzwolenia na dwa sposoby zabrałby tej parze sens. Stąd dwie rzeczy, które
wyglądają na drobiazgi i nie są: komplet siedmiu dni normalizuje się do ich braku, a `daily`
dni tygodnia nie dostaje w ogóle, bo `daily` z dniami to jest `weekly`.

Dwa scenariusze w mojej własnej delcie opisywały mechanikę formularza zamiast własności i
kod ich nie potwierdził — poprawione w trakcie, nie obejście. Znalezisk w kodzie nie ma;
są trzy rzeczy do zapisania, żeby następny czytelnik nie wziął ich za przeoczenia.

Czego nie ma: **przebiegu na produkcji** (4.5). Harmonogram `35 * * * *`, od którego się to
zaczęło, dalej chodzi siedem dni w tygodniu, dopóki operator go nie przestawi po wdrożeniu.

## Verified

Uruchomione 17 sierpnia 2026 na gałęzi `change/weekdays-on-the-shorter-rhythms`:

- `modules/teams`: `uv run ruff check .` — „All checks passed!". `uv run pyright` —
  **0 errors**. `uv run pytest -q` — **411 passed**. `uv run pytest -m db -q` —
  **173 passed**, 238 deselected, przeciw jednorazowemu PostgreSQL-owi w kontenerze.
- `modules/terminal`: `tsc -b --noEmit` czysto, `eslint .` czysto,
  `node scripts/contract.mjs check` — „Every contract is up to date.",
  `vitest run` — **905 passed** w 57 plikach (901 przed zmianą).
- `openspec validate weekdays-on-the-shorter-rhythms --strict` — „is valid", także po
  poprawkach delty opisanych w `Findings`.
- Kontrakt przegenerowany (`node scripts/contract.mjs generate`): jedyna różnica w
  `contract.teams.generated.ts` to opis `Recurrence`. **Żadnego pola, żadnego typu** — bo
  `weekdays` było już publikowane jako `number[] | null` dla wszystkich rytmów; to
  walidator decydował, które je przyjmują, i to on się zmienił.
- **Nie uruchamiano:** niczego na produkcji ani na uruchomionym lokalnie stosie. Zegar
  nie był budzony — dowodem, że wyzwolenia omijają weekend, jest arytmetyka
  (`test_schedule_timing.py`, 200 kolejnych wyzwoleń), nie przebieg.

## Findings

| Severity | Where | Finding | Status |
|---|---|---|---|
| **Medium** | `specs/terminal-teams-schedules/spec.md` (delta tej zmiany) | Dwa scenariusze, które sam napisałem, opisywały mechanikę interfejsu, a nie własność: „komplet dni MUST być pokazany jako brak ograniczenia, a nie siedem zaznaczonych" (formularz z siedmioma przełącznikami pokazuje siedem zaznaczeń i inaczej nie może) oraz „odznaczenie wszystkich dni MUST NOT dać się zapisać" (kod nie dopuszcza odznaczenia **ostatniego** dnia, więc stan zerowy nie powstaje i żaden komunikat nie pada). Wymaganie, którego implementacja nie potwierdza, jest gorsze niż jego brak — zostałoby odhaczone i nikt by nie zauważył. | FIXED w trakcie: pierwsze mówi teraz, że formularz MUST NOT trzymać dwóch stanów jednego wyzwolenia; drugie, że ostatniego dnia MUST NOT dać się odznaczyć. Oba są tym, czego kod naprawdę pilnuje, i oba są mocniejsze niż to, co zastąpiły. |
| — | — | Znalezisk w kodzie nie ma. | — |

Trzy rzeczy, które wyglądają jak przeoczenia i nimi nie są — zapisane, żeby nie sprawdzać
ich drugi raz:

- **Harmonogram, który dotąd nie miał rytmu, może go teraz dostać.** Wyrażenie
  `35 * * * 1,2,3,4,5` wpisane kiedyś ręcznie pod „Advanced" wracało jako rytm pusty, bo
  gałąź `weekly` próbowała wziąć `int("*")`. Teraz otwiera się w kreatorze jako rytm
  godzinowy z dniami. Jest to zgodne z wymaganiem („rytm spoza kreatora" dotyczy wyrażeń,
  których kreator opisać **nie umie**), ale operator zobaczy formularz tam, gdzie widział
  pole tekstowe. Zakres `1-5` zapisany ręcznie zostaje pod „Advanced", bo postać kanoniczna
  jest listą.
- **`weekly` z siedmioma dniami zostaje siedmioma dniami**, choć krótsze rytmy się
  normalizują. To nie jest niekonsekwencja: `0 9 * * 0,1,2,3,4,5,6` to inne wyrażenie niż
  `0 9 * * *`, więc każde ma dokładnie jeden rytm i nic się nie dubluje. Gdyby `weekly` też
  normalizować, straciłby wymagane pole.
- **Przejście z rytmu godzinowego bez dni na tygodniowy daje poniedziałek–piątek**, a nie
  siedem dni. Zawężenie, ale widoczne: przełączniki od razu pokazują, co jest zaznaczone,
  a poniedziałek–piątek był domyślnym wyborem tego rytmu jeszcze przed tą zmianą.

## Spec coverage

| Requirement / Scenario | Proven by |
|---|---|
| **teams-schedules** — Harmonogram da się opisać rytmem, a moduł zna oba zapisy | `test_recurrence.py` — round-trip każdego rytmu w obie strony (`RHYTHMS`, teraz z trzema wpisami z dniami) |
| — Harmonogram zapisany rytmem | `test_schedules_routes.py::test_a_schedule_saved_as_a_rhythm_comes_back_as_the_same_rhythm` |
| — Rytm godzinowy ograniczony do dni handlowych | `test_schedules_routes.py::test_an_hourly_rhythm_carries_the_days_it_was_saved_with` (wyrażenie `35 * * * 1,2,3,4,5` i ten sam rytm z odczytu); `test_schedule_timing.py::test_an_hourly_expression_with_weekdays_steps_over_the_weekend` (po piątku 21:35 jest poniedziałek, nie sobota) |
| — Rytm krótszy niż godzina bez dni tygodnia | `test_recurrence.py::test_no_weekdays_is_every_day_and_stays_absent` (obie odmiany rytmu) |
| — Wszystkie dni tygodnia wskazane | `test_recurrence.py::test_every_day_named_is_the_same_as_none_named`, a od drugiej strony `::test_a_weekly_rhythm_keeps_all_seven_days` |
| — Dni tygodnia przy rytmie dobowym | `test_recurrence.py::test_a_daily_rhythm_refuses_weekdays_and_names_the_one_that_takes_them`, `::test_a_monthly_rhythm_refuses_weekdays_too`, na drucie `test_schedules_routes.py::test_a_daily_rhythm_with_weekdays_is_refused` (422 z nazwą `weekly`) |
| — Wyrażenie spoza rytmów kreatora | `test_recurrence.py::test_an_expression_outside_the_rhythms_is_no_rhythm`, wzbogacone o `35 * * * 1-5` i `35 * * * 0,1,2,3,4,5,6`; `test_schedules_routes.py::test_a_schedule_saved_as_an_expression_outside_the_rhythms_carries_no_rhythm` |
| **terminal-teams-schedules** — Harmonogram układa się rytmem i godziną | `SchedulesPanel.test.tsx` → „posts a rhythm the operator chose, with no cron expression typed anywhere" (bez zmian), „turns the weekend off on an hourly rhythm, without a cron expression" |
| — Weekend wyłączony przy rytmie godzinowym | `SchedulesPanel.test.tsx` → „turns the weekend off on an hourly rhythm, without a cron expression" |
| — Operator zaznacza z powrotem wszystkie dni | `SchedulesPanel.test.tsx` → „sends every day as no days at all, so one trigger has one shape" |
| — Rytm dobowy nie ma dni tygodnia | `SchedulesPanel.test.tsx` → „offers no days at all under the daily rhythm" |
| — Operator odznacza ostatni dzień | `SchedulesPanel.test.tsx` → „keeps the last day rather than letting a schedule fire on none" |
| — Podgląd nadąża za dniami | `test_schedules_routes.py::test_a_rhythm_with_weekdays_can_be_previewed_before_it_is_saved` — **częściowo**: dowodzi, że dni przechodzą przez trasę podglądu, ale sufit 20 wyzwoleń dla rytmu godzinowego nie musi sięgnąć soboty. Sam weekend jest dowiedziony w arytmetyce → luka |
| — Rytm spoza kreatora | `SchedulesPanel.test.tsx` → „opens a schedule the wizard has no rhythm for on its own expression, and saves it unchanged" |

## Gaps

- **4.5 niewykonane.** Na produkcji nic nie zostało przestawione: harmonogram `35 * * * *`
  dalej budzi zespół w sobotę. Po wdrożeniu `teams` i terminala trzeba go otworzyć w
  kreatorze, odznaczyć sobotę i niedzielę i sprawdzić, że najbliższe wyzwolenia ich nie
  zawierają. To jest ten sam przebieg, którym operator zauważył problem.
- **Podgląd w kreatorze nie jest sprawdzony przez weekend.** Trasa przyjmuje sufit 20
  wyzwoleń, a 20 godzinowych nie musi przekroczyć piątku. Test tras dowodzi, że dni
  docierają; że podgląd ich słucha, wynika z tego, że liczy je ten sam kod co zegar
  (`next_fire_after`), a nie z asercji na sobocie.
- **Zegar nie był uruchamiany z tym rytmem.** `_fire_schedule` dostaje wyrażenie i o
  rytmach nie wie, więc nie ma tam czego zmieniać — ale to jest rozumowanie, nie test.
