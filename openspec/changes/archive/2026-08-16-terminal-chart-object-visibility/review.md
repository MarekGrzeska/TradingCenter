## Verdict

Gaszenie naniesionych obiektów bez ich kasowania jest zaimplementowane w całości: kolumna
`hidden` na rysunku, `hide`/`show` w `draw_on_chart` pod tymi samymi regułami, które to
narzędzie już miało, `hidden` w odczycie modelu i na drucie, oraz przełącznik w liście
i na karcie obiektu. Rysunki stojące dziś w bazie wychodzą z migracji zapalone, czyli
wyglądają dokładnie tak, jak wyglądały.

Dwie rzeczy, które w tej zmianie działają inaczej, niż podpowiadałaby symetria, i są tego
świadome. **Zgaszenie nie zdejmuje wskazania**, a usunięcie zdejmuje: karta zostaje
otwarta z przyciskiem zamienionym na „Show", bo gaszenie jest odwracalne i najbliższa
droga powrotna musi być tam, gdzie padło. Pierwsza wersja delty mówiła odwrotnie i została
poprawiona jeszcze przed implementacją. **Sufit stu obiektów liczy zgaszone**, więc
operator, który dobił do stu i pogasił połowę, nadal nie postawi kolejnego — sufit jest
o zapisie i o odczycie bez kresu, nie o gęstości ekranu.

Jedno realne znalezisko z przeglądu diffu, naprawione przed napisaniem tego dokumentu —
patrz Findings.

Ręczne przejście na żywym stacku (task 6.3) **nie zostało wykonane** — wymaga Dockera,
sesji Capital i klucza OpenAI, i jest czynnością operatora. Patrz Gaps.

## Verified

- `modules/terminal`: `pnpm test` (vitest run) — **739 passed** w 48 plikach.
- `modules/terminal`: `pnpm lint` (eslint .) — bez zastrzeżeń.
- `modules/terminal`: `pnpm typecheck` (tsc -b --noEmit) — bez błędów.
- `modules/terminal`: `pnpm contract:check` — „Contract is up to date" (`market_data/contract.py`
  nietknięty; kontrakt agenta terminal trzyma ręcznie po obu stronach).
- `modules/agent`: `uv run pytest` — **318 passed**, 2 warnings (nieistotne,
  `httpx`/`pydantic-settings`).
- `modules/agent`: `uv run pytest -m db` — **216 passed**, 102 deselected. Migracja `0009`
  zastosowała się w kontenerze; `test_migration_seeds_the_current_text` czyta z niej `v9`.
- `modules/agent`: `uv run ruff check .` — All checks passed.
- `modules/agent`: `uv run pyright` — 0 errors, 0 warnings, 0 informations.
- `openspec validate terminal-chart-object-visibility --strict` — valid.

## Findings

| Severity | Where | Finding | Status |
|---|---|---|---|
| Medium | `agent/tools/drawings.py` — `DrawOnChartTool.call` | Ten sam identyfikator w `remove` i w `hide` przechodził przez sprawdzenie sprzeczności, które patrzyło wyłącznie na parę `hide`/`show`. Usunięcie biegło pierwsze, a gaszenie odbijało się o „no drawing on US100 with id #7" — zdanie, które każe modelowi szukać złego identyfikatora zamiast spojrzeć na dwie listy, które sam napisał. Transakcja cofała wszystko, więc nic nie ginęło; myląca była odmowa, czyli jedyny kanał, którym model się uczy. Sprawdzenie obejmuje teraz każdą parę z trzech list. | FIXED — `0422d0e` |
| Info | `ChartDrawings.patch(id, {hidden})` zamiast `setHidden` | `tasks.md` 3.2 zapowiadał osobną metodę w sklepie. Wylądowało jako pole na istniejącej łatce, zgodnie z `design.md` („Operator gasi przez `PATCH /drawings/{id}`, nie przez nową trasę"): druga metoda byłaby drugimi drzwiami do jednej trasy. Zadanie odhaczone, bo zdolność jest — nazwa nie. | Świadome odstępstwo |

Poza tym: bez znalezisk. Rzeczy sprawdzone i uznane za poprawne: `hidden` w domenie siedzi
na `ChartDrawing`, nie w geometrii, więc zmiana kształtu nie ma gdzie go zgubić; `total`
w potwierdzeniu narzędzia liczy się po gaszeniu, a gaszenie liczby nie rusza, więc jest
poprawne; `useMemo` filtrujące zgaszone oddaje tę samą referencję, gdy nic nie jest
zgaszone, więc efekt synchronizujący nie startuje bez powodu.

## Spec coverage

| Requirement / Scenario | Proven by |
|---|---|
| **agent-chart-drawings — Rysunki są trwałe i mają własną tożsamość** | |
| Rysunek przeżywa odświeżenie strony | `tests/test_chart_drawings_store.py::test_a_level_survives_the_round_trip` (sprzed tej zmiany) |
| Rysunek przeżywa rozmowę | `tests/test_chart_drawings_store.py::test_a_drawing_outlives_the_session_that_made_it` (sprzed tej zmiany) |
| Zgaszenie przeżywa odświeżenie strony | `tests/test_drawings_router.py::test_the_operator_hides_a_drawing_and_shows_it_again` (odczyt po zgaszeniu idzie osobnym żądaniem, czyli tą samą drogą co po F5) |
| Zapalony rysunek jest tym samym rysunkiem | `tests/test_chart_drawings_store.py::test_hiding_and_showing_leave_everything_else_alone`; `tests/test_drawings_tool.py::test_showing_gives_back_the_same_drawing` |
| Sufit rysunków na instrumencie | `tests/test_drawings_tool.py::test_the_ceiling_refuses_the_whole_call` (sprzed tej zmiany) |
| Zgaszone liczą się do sufitu | `tests/test_drawings_tool.py::test_hidden_drawings_still_count_towards_the_ceiling`; `tests/test_chart_drawings_store.py::test_count_counts_hidden_drawings_too` |
| **agent-chart-drawings — Agent stawia i kasuje rysunki narzędziem** | |
| Agent stawia wsparcie i opór | `tests/test_drawings_tool.py::test_two_levels_in_one_call_both_land` (sprzed tej zmiany) |
| Agent kasuje rysunek, który sam postawił | `tests/test_drawings_tool.py::test_a_removal_and_an_addition_travel_together` (sprzed tej zmiany) |
| Agent gasi rysunek zamiast go kasować | `tests/test_drawings_tool.py::test_hiding_takes_a_drawing_off_the_chart_and_keeps_it`; `tests/test_drawings_tool.py::test_the_confirmation_says_hidden_rather_than_removed` |
| Agent zapala z powrotem | `tests/test_drawings_tool.py::test_showing_gives_back_the_same_drawing` |
| Zgaszenie i zapalenie jednego rysunku naraz | `tests/test_drawings_tool.py::test_hiding_and_showing_one_id_at_once_is_refused`; `tests/test_drawings_tool.py::test_removing_and_hiding_one_id_at_once_is_refused_by_name` |
| Wywołanie z jednym rysunkiem nie do przyjęcia | `tests/test_drawings_tool.py::test_a_colour_the_chart_cannot_draw_is_refused_and_nothing_lands` (sprzed tej zmiany) |
| Gaszenie identyfikatora, którego nie ma | `tests/test_drawings_tool.py::test_hiding_an_id_that_is_not_there_takes_back_the_others`; `tests/test_drawings_tool.py::test_an_id_from_another_instrument_is_not_hideable` |
| Agent nie kasuje przez pominięcie | `tests/test_drawings_tool.py::test_adding_does_not_remove_what_is_already_there` (sprzed tej zmiany) |
| Agent nie gasi przez pominięcie | `tests/test_drawings_tool.py::test_hiding_does_not_touch_what_it_was_not_told_to` |
| (gaszenie i rysowanie w jednym wywołaniu) | `tests/test_drawings_tool.py::test_hiding_and_drawing_travel_together` |
| (schemat pokazuje modelowi obie operacje) | `tests/test_drawings_tool.py::test_the_tool_offers_hide_and_show_beside_remove` |
| **agent-chart-drawings — Agent odczytuje rysunki narzędziem** | |
| Pytanie o naniesione poziomy | `tests/test_drawings_tool.py::test_the_read_carries_ids_shapes_and_labels` |
| Odczyt mówi, który rysunek jest zgaszony | `tests/test_drawings_tool.py::test_the_read_says_which_drawings_are_hidden` |
| Odczyt instrumentu spoza ekranu | `tests/test_drawings_tool.py::test_the_read_answers_without_an_archive` (sprzed tej zmiany) |
| Odczyt, potem skasowanie | `tests/test_drawings_tool.py::test_read_then_remove_uses_the_same_id` (sprzed tej zmiany) |
| Odczyt, potem zgaszenie | `tests/test_drawings_tool.py::test_the_read_says_which_drawings_are_hidden` razem z `test_hiding_takes_a_drawing_off_the_chart_and_keeps_it` — patrz Gaps |
| **terminal-chart — Wykres rysuje obiekty naniesione na instrument** | |
| Poziom po zmianie interwału | `Chart.test.tsx::keeps the objects through a resolution change` |
| Linia trendu między dwoma punktami | `TrendlinePrimitive.test.ts::draws a segment between its two points and stops there` |
| Naniesiony poziom obok policzonego | `RayPrimitive.test.ts::draws an operator's level heavier and unbroken, an indicator's thin and dashed` |
| Zgaszony obiekt nie jest rysowany | `Chart.test.tsx::gives a hidden object no primitive at all`; `Chart.test.tsx::takes the primitive off when an object is hidden, and gives it back on show` |
| Kliknięcie tam, gdzie stał zgaszony obiekt | Brak prymitywu, więc `hitTest` nie ma czego pytać — patrz Gaps |
| Etykieta ceny przy osi | `RayPrimitive.test.ts::says the price, coloured by the side of the market it sits on` |
| Obiekt zaczynający się poza widokiem | `RayPrimitive.test.ts::keeps the caption on screen for a level starting off the left edge` |
| Kolor obiektu po usunięciu innego | `theme.test.ts::gives one id one colour, whatever else is on the chart` |
| Kolor obiektu po zgaszeniu innego | `Chart.test.tsx::takes the primitive off when an object is hidden, and gives it back on show` (ta sama instancja prymitywu zostaje, więc jej kolor nie mógł się ruszyć) |
| Zmiana symbolu | `Chart.test.tsx::replaces them when the symbol changes` |
| Nieudany odczyt obiektów | `DrawingList.test.tsx::a failed read says so, and does not read as an empty instrument` |
| **terminal-chart — Operator zarządza naniesionymi obiektami z listy** | |
| Operator usuwa poziom z listy | `DrawingList.test.tsx::removes one object` |
| Operator poprawia cenę z listy | `DrawingList.test.tsx::corrects a price, sending only what moved` |
| Operator gasi poziom z listy | `DrawingList.test.tsx::hides a row's object through patch, not through remove`; `Chart.test.tsx::shows a hidden object on the list, so there is a way back to it` |
| Operator zapala poziom z listy | `DrawingList.test.tsx::keeps a hidden object on the list, marked out and offering to bring it back` |
| Usunięcie się nie powiodło | `DrawingList.test.tsx::says a removal failed and leaves the row where it was` |
| Zgaszenie się nie powiodło | `DrawingList.test.tsx::says a failed hiding failed and leaves the row lit`; `drawingsStore.test.ts::says a failed hiding failed and leaves the list as it was` |
| Instrument bez obiektów | `DrawingList.test.tsx::an instrument with nothing on it says so` |
| Instrument z samymi zgaszonymi obiektami | `DrawingList.test.tsx::an instrument with everything hidden does not read as an empty one` |
| **terminal-chart-objects — Wskazany obiekt mówi, czym jest** | |
| Opis wskazanego obiektu | `DrawingCard.test.tsx::describes a level: its shape, its price, its caption and when it was drawn` |
| Poprawienie z opisu | `DrawingCard.test.tsx::corrects a price the same way the list does, sending only what moved` |
| Zgaszenie z opisu | `DrawingCard.test.tsx::hides through the same patch route a price correction takes`; `DrawingCard.test.tsx::does not close the card, the way removing does`; `Chart.test.tsx::keeps the picked object's card open when it is hidden` |
| Zapalenie z opisu tuż po zgaszeniu | `DrawingCard.test.tsx::offers to bring a hidden object back, and says it is hidden` |
| Usunięcie z opisu | `DrawingCard.test.tsx::removes the object through the same call the list makes`; `Chart.test.tsx::still lets go of an object that is removed while picked` |
| Nieudane poprawienie z opisu | `DrawingCard.test.tsx::says a correction failed and leaves the object as it was` |
| Nieudane zgaszenie z opisu | `DrawingCard.test.tsx::says a failed hiding failed, and leaves the object alone` |
| Wskazany obiekt zgaszony skądinąd | `Chart.test.tsx::keeps the picked object's card open when it is hidden` (zgaszenie przychodzi z zewnątrz, jako nowa lista) |
| (prompt mówi modelowi, że gaszenie jest odwracalne) | `tests/test_prompt_store.py::test_the_drawing_paragraph_says_hiding_is_undoable_and_removing_is_not` |
| (druty i sklep) | `agentApi.test.ts::maps a level, its moments as epoch seconds`; `drawingsStore.test.ts::hides through patch and re-reads, rather than editing the copy in hand`; `drawingsStore.test.ts::counts a hidden object as still there, not as removed` |

## Gaps

- **Task 6.3 — przejście ręką na żywym stacku.** Nie wykonane. Wymaga Dockera, sesji
  Capital i klucza OpenAI. Sprawdza to, czego jsdom nie dotknie: czy zgaszenie faktycznie
  zdejmuje linię z prawdziwego canvasu, czy karta z „Show" wygląda jak droga powrotna,
  i czy zgaszenie przez agenta dochodzi do otwartego terminala bez odświeżenia. Czynność
  operatora.
- **„Kliknięcie tam, gdzie stał zgaszony obiekt"** — bez własnego testu. Zgaszony obiekt
  nie ma prymitywu (`Chart.test.tsx::gives a hidden object no primitive at all`), a `hitTest`
  jest metodą prymitywu, więc nie ma czego zapytać. Dowiedzione przez konstrukcję, nie
  przez test, i tak jest to tutaj zapisane.
- **„Odczyt, potem zgaszenie"** — dwa testy pokrywają obie połowy (odczyt niesie stan,
  gaszenie po identyfikatorze działa), ale żaden nie przechodzi tej drogi jednym ciągiem
  tak, jak `test_read_then_remove_uses_the_same_id` robi to dla kasowania. Identyfikator
  jest ten sam w obu operacjach — to jedna kolumna — więc luka jest wąska, ale jest.
- **„Zgaszenie przeżywa odświeżenie strony"** — dowiedzione przez ponowny odczyt z bazy
  w teście routera, a nie przez faktyczne przeładowanie terminala. To jest ta sama droga,
  którą chodzi F5, ale terminal jej w teście nie przechodzi.
