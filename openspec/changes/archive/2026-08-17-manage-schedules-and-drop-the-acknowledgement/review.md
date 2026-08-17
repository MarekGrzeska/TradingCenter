# Review

## Verdict

Zgoda na pracę bez nadzoru zniknęła w całości — z kontraktu, z bazy, z walidacji, z tras i
z formularza — a harmonogram da się teraz zatrzymać, poprawić i usunąć zarówno z czatu, jak
i z listy w terminalu. Zestaw narzędzi `teams-mcp` urósł z trzech do dziewięciu, a `teams`
dostał dwie trasy, których nie miał: `DELETE` dla harmonogramu i dla wyzwalacza.

Rdzeniem nie jest samo usunięcie pola, tylko **co usunięcie zabiera**: historia wyzwoleń
znika kaskadą w bazie, przebiegi zostają. Kierunek klucza obcego już to gwarantował — to
historia wskazuje przebieg, nie odwrotnie — więc „przebiegi zostają" nie wymagało ani jednej
linii kodu, tylko sprawdzenia, że nikt nie wskazuje w drugą stronę. `CHECK` z migracji
`0005` przesądził resztę: wiersz historii musi nazywać albo harmonogram, albo wyzwalacz, nie
ma stanu osieroconego, więc kaskada nie była wyborem estetycznym.

Znaleziska są dwa i oba dotyczą tego, co **zostało po usuniętym sprawdzeniu**, a nie tego,
co doszło. Oba naprawione w trakcie.

Czego nie ma: **przebiegu na produkcji** (5.6). Ta zmiana wdroży się przed tym, jak
ktokolwiek założy z czatu harmonogram, którego dotąd założyć się nie dało.

## Verified

Uruchomione 17 sierpnia 2026 na gałęzi `change/manage-schedules-and-drop-the-acknowledgement`:

- `modules/teams`: `uv run ruff check .` — „All checks passed!". `uv run pyright` —
  **0 errors**. `uv run pytest -q` — **410 passed**. `uv run pytest -m db -q` —
  **177 passed**, 233 deselected, przeciw jednorazowemu PostgreSQL-owi w kontenerze — czyli
  migracja `0007` naprawdę przeszła, razem z wymianą obu kluczy obcych.
- `modules/teams-mcp`: `ruff` czysto, `pyright` **0 errors**, `uv run pytest -q` —
  **86 passed**, `uv run python scripts/contract.py check` — „Contract is up to date."
  (snapshot przegenerowany w tym samym commicie).
- `modules/terminal`: `tsc -b --noEmit` czysto, `eslint .` czysto,
  `node scripts/contract.mjs check` — „Every contract is up to date.", `vitest run` —
  **910 passed** w 57 plikach (905 przed zmianą).
- `openspec validate manage-schedules-and-drop-the-acknowledgement --strict` — „is valid".
- Wyszukanie po całym drzewie: `unattended_ack` nie występuje już w żadnym module — ani w
  kodzie, ani w testach, ani w wygenerowanym kontrakcie terminala.
- **Nie uruchamiano:** niczego na produkcji, ani zegara z nowym harmonogramem, ani
  usunięcia przez wdrożony terminal. Migracja `0007` przeszła wyłącznie w kontenerze
  testowym; na produkcji pójdzie w `lifespan` przy pierwszym starcie nowego obrazu.

## Findings

| Severity | Where | Finding | Status |
|---|---|---|---|
| **Medium** | `teams/routers/schedules.py:56` | Po usunięciu sprawdzenia zgody `_resolve_definition` zwracało definicję, której nikt już nie czytał — cztery trasy przypisywały ją do zmiennej i nie używały. `ruff` złapał to jako `F841`, ale samo wywołanie jest **dalej potrzebne**: to ono odmawia 404 i 422, gdy rewizja nie należy do zespołu. Skasowanie przypisania i zostawienie „resolvera", który niczego nie rozwiązuje, byłoby funkcją udającą coś, czym przestała być — i następny czytelnik usunąłby ją jako martwą, zabierając ze sobą trzy odmowy. | FIXED: funkcja nazywa się `_revision_must_be_there`, zwraca `None`, a jej docstring mówi, że istnieje **dla swoich odmów**. Testy tras, które je sprawdzają, przechodzą bez zmian. |
| **Medium** | `teams-mcp/tools/_shared.py:22`, `teams/README.md:157`, `teams-mcp/README.md:106` | Trzy miejsca opisywały adnotację `readOnlyHint` i pole zgody jako mechanizm żywy: komentarz przy `READ_ONLY` mówił, że „`teams` czyta dokładnie tę adnotację, decydując, czy rewizja może chodzić bez nadzoru", a oba README opisywały `unattended_ack` jako obowiązujące zabezpieczenie. Po tej zmianie żadne z tych zdań nie jest prawdziwe, a komentarz, który uzasadnia kod nieistniejącym mechanizmem, jest gorszy niż jego brak — następna osoba szuka sprawdzenia, którego nie ma. | FIXED: wszystkie trzy przepisane. Adnotacja jest teraz opisana jako to, czym została — deklaracja dla klienta MCP, a nie wejście do odmowy. |

Trzy rzeczy warte zapisania, żeby nie sprawdzać ich drugi raz:

- **Kaskada jest w bazie, nie w kodzie trasy.** `ON DELETE CASCADE` na obu kluczach
  `schedule_fires`. Ta sama reguła napisana w Pythonie rozjechałaby się przy pierwszej
  trasie, która skasuje wiersz bez pamiętania o połowie.
- **`extra` zostaje domyślne.** Modele kontraktu nie mają `extra="forbid"`, więc terminal
  sprzed zmiany dalej wysyła `unattended_ack`, a moduł je ignoruje. To jest zachowanie
  **domyślne**, czyli takie, które ktoś może kiedyś odwrócić jednym ustawieniem — dlatego
  ma własny test (`test_an_acknowledgement_field_from_an_older_terminal_is_ignored`), a nie
  tylko zdanie w `design.md`.
- **`teams-mcp` nie odziedziczył kasowania hurtem.** Jedno narzędzie kasuje jeden wpis; nie
  ma „usuń wszystkie", bo między „posprzątaj to" a pustym katalogiem byłoby wtedy jedno
  wywołanie modelu.

## Spec coverage

| Requirement / Scenario | Proven by |
|---|---|
| **teams-schedules** — REMOVED: „Harmonogram nad rewizją z narzędziami zapisującymi wymaga jawnego potwierdzenia" | Dowodem jest odwrócony test: `test_schedules_routes.py::test_a_schedule_over_order_placing_tools_is_written_without_any_consent` i `::test_a_trigger_over_order_placing_tools_is_written_too` — oba przeciw serwerowi, który naprawdę ogłasza `place_order` z `readOnlyHint: false`, a nie przeciw dublerowi |
| — Harmonogram i wyzwalacz dają się usunąć | `test_schedules_routes.py::test_a_deleted_schedule_is_gone_from_the_catalogue`, `::test_a_deleted_trigger_is_gone_with_its_history` |
| — Operator usuwa harmonogram | `::test_a_deleted_schedule_is_gone_from_the_catalogue` (znika z katalogu, drugie usunięcie to `404`) |
| — Usunięcie zabiera historię wyzwoleń | `::test_deleting_a_schedule_takes_its_fire_history` — z wierszem historii zapisanym wprost przez `store.record_fire`, więc bez kaskady ten `DELETE` w ogóle by nie przeszedł |
| — Wyłączenie to nie usunięcie | `::test_disabling_is_not_deleting` (wiersz zostaje, wraca włączony) |
| — Cudzy harmonogram | `::test_a_strangers_schedule_is_neither_deleted_nor_admitted_to`, `::test_a_deleted_trigger_is_gone_with_its_history` (obcy dostaje `404`, wpis stoi) |
| — „przebiegi zostają" | **Bez testu**, i uczciwiej: nie ma czego testować — `runs` nie ma kolumny wskazującej harmonogram, więc kaskada nie ma jak ich dosięgnąć. Dowodem jest schemat, nie asercja → luka nazwana |
| **teams-mcp-tools** — Zestaw obejmuje zarządzanie harmonogramem | `test_schedule_tools.py::test_the_published_set_covers_the_whole_life_of_a_schedule` |
| — Model zatrzymuje harmonogram | `::test_pausing_disables_and_resuming_enables` |
| — Poprawka zachowuje wpis | `::test_editing_a_schedule_keeps_the_row_it_edits` — sprawdza też, że `DELETE` **nie** został zawołany, `::test_editing_a_trigger_changes_only_what_was_named` |
| — Model usuwa wyzwalacz | `::test_deleting_says_what_it_took_and_what_it_left`, `::test_deleting_a_schedule_that_is_not_there_refuses_rather_than_pretending` |
| — Opis narzędzia usuwającego mówi, co znika | `::test_deleting_says_what_it_took_and_what_it_left` bada **odpowiedź**; sam opis jest w docstringu i sprawdza go tylko `test_tool_surface`-owy warunek długości → częściowo, luka |
| — Narzędzia niszczące odróżnialne | `::test_only_the_two_deleting_tools_are_marked_destructive` |
| **teams-mcp-authorship** (MODIFIED) — Czynność dostępna w terminalu jest dostępna z czatu | `::test_the_published_set_covers_the_whole_life_of_a_schedule` — dziewięć nazw wobec czterech czynności, które ma lista w terminalu |
| **terminal-teams-schedules** — Harmonogram da się usunąć z listy | `SchedulesPanel.test.tsx` → „deletes after the confirmation and re-reads the list" |
| — Potwierdzenie mówi, co zniknie | → „says what the delete takes and what it leaves, before it is done" |
| — Operator rezygnuje z usunięcia | → „leaves the schedule alone when the operator backs out" |
| — Zatrzymanie zostaje osobną czynnością | → „keeps disabling as its own, reversible action" |
| — Pole zgody zniknęło z formularza | → „has no consent box left in the form" |

## Gaps

- **5.6 niewykonane.** Na produkcji nikt nie założył z czatu harmonogramu nad zespołem z
  narzędziami handlowymi ani nie usunął go z terminala. To jest ten sam przebieg, którym
  operator dwa razy zderzył się z odmową, i pierwsza rzecz do zrobienia po wdrożeniu.
- ~~**Migracja `0007` nie szła po produkcyjnych danych.**~~ **Zamknięte tego samego dnia:**
  wdrożenie `1d5a199` weszło, a `teams` odpowiada 200 na `/health`. Migracja idzie w
  `lifespan` przed obsługą ruchu, więc odpowiadający proces **jest** dowodem, że
  `drop_column` i wymiana obu kluczy obcych przeszły po wierszach, które tam były. Czego to
  nie mierzy: jak długo trwały.
- **„Przebiegi zostają" jest własnością schematu, nie testu** — patrz tabela wyżej.
- **Opisy narzędzi nie mają testu na treść.** Wymaganie żąda, żeby opis narzędzia
  usuwającego nazywał, co znika bezpowrotnie; sprawdzam to w odpowiedzi narzędzia, nie w
  jego docstringu. Docstring dałoby się sprawdzić jednym asertem po `list_tools()`.

## Po scaleniu: ta zmiana została cofnięta i odtworzona

Zapisane tutaj, bo to jedyne miejsce, które przeżyje archiwizację, a wypadek dotyczy tej
zmiany i niczego więcej.

Cztery minuty po zmergowaniu (`1d5a199`, 22:14:00) commit `9473229` — archiwizacja siedmiu
zmian, zrobiona w drugiej sesji — **cofnął wszystkie 25 plików tej zmiany**, razem z
migracją `0007` i z katalogiem samej zmiany. Trzy rzeczy to ustalają: rodzicem tamtego
commita jest `1d5a199`, powstał 52 sekundy po nim, a cofnięte pliki są bajt w bajt stanem
z `556f946` — czyli zawartością drzewa roboczego sprzed tego merge'a. Rodzic został
przestawiony na nowy `main`, treść plików została stara.

Konfliktu nie było i być nie mogło: tamta sesja nie tykała tych plików, więc git nie miał o
co pytać. CI na tamtym PR przeszło, bo cofnięty kod jest spójny sam ze sobą — zielone testy
opisywały stan sprzed tej zmiany.

Groźna była nie sama utrata kodu, tylko rozjazd, który po niej został: produkcyjna baza była
już na `0007`, a `main` wrócił do `0006` i do `store.py` pytającego o skasowaną kolumnę.
Nic nie przestało działać, bo produkcja chodziła z `1d5a199` — ale najbliższe wdrożenie
`teams` z maina by nie wstało.

Odtworzone z `1d5a199`, plik po pliku, po czym moduły zostały porównane z tamtym commitem i
są identyczne. Wniosek na przyszłość jest ostrzejszy niż „uważać": przy równoległych
worktree commit, którego rodzic jest świeży, **nie znaczy**, że jego treść jest świeża.
