## Verdict

Kadr — nawigacja po wykresie przez agenta — jest zaimplementowana od zapisu przez `set_chart`
po zastosowanie na ekranie: trzy kształty (`from`/`to`, `around`+`bars`, `last_bars`),
dociąganie historii przez istniejący pager `useOlderBars`, zachowanie kadru przy zmianie
interwału, i migawka niosąca widoczny fragment osi z powrotem do modelu. Jeden realny błąd
znaleziony w trakcie tego review (kadr `around`+`bars` pokazywał o jedną świecę za dużo dla
parzystego `bars`) został naprawiony przed napisaniem tego dokumentu — patrz Findings.

Ręczne przejście na żywym stacku (task 9.3) **nie zostało wykonane przeze mnie** — operator
testuje je samodzielnie równolegle z tym review. Podczas pierwszego testu zgłosił, że
przesuwanie wykresu przez agenta „nie działa" — agent odpowiadał potwierdzeniem, ale wykres
się nie ruszał. Zdiagnozowane jako najpewniej stary, nierestartowany proces terminala/agenta
(operator niepewny, czy stack był restartowany po tej sesji zmian) — potwierdzenie w
odpowiedzi agenta pochodzi wyłącznie z zapisu po stronie backendu (`_confirmation()` w
`chart.py` odpala się, zanim terminal w ogóle odczyta polecenie), więc nie dowodzi niczego
o froncie. Nie jest to jeszcze potwierdzone jako zamknięte — wynik ręcznego testu po
restarcie stacku jest w toku poza tym dokumentem.

Luka opisana pierwotnie jako rezydualna — kadr `from`/`to` sięgający głębiej, niż pager
zdąży dociągnąć w limicie `MAX_PAGES=20` — **została zamknięta** przy okazji review zmiany
`agent-chart-drawings`, patrz Findings, wiersz drugi.

## Verified

- `modules/agent`: `uv run pytest` — **233 passed**, 2 warnings (nieistotne, `httpx`/`pydantic-settings`).
- `modules/agent`: `uv run pytest -m db` — **131 passed**, 102 deselected.
- `modules/agent`: `uv run ruff check .` — All checks passed.
- `modules/agent`: `uv run pyright` — 0 errors, 0 warnings, 0 informations.
- `modules/terminal`: `pnpm test` (vitest) — **619 passed** w 44 plikach.
- `modules/terminal`: `pnpm lint` (eslint .) — bez zastrzeżeń.
- `modules/terminal`: `pnpm typecheck` (tsc -b --noEmit) — bez błędów.
- Task 9.3 (ręczne przejście na żywym stacku) — **nie uruchomione w tej sesji**; operator
  testuje równolegle, pierwszy wynik (przed restartem stacku) opisany w Verdict.

## Findings

| Severity | Where | Finding | Status |
|---|---|---|---|
| Medium | `modules/terminal/src/chart/Chart.tsx`, `applyFocusToView` (`around`+`bars` gałąź) | `{from: index - half, to: index + half}` dla `half = floor(bars/2)` daje `bars+1` świec dla każdego parzystego `bars` (np. `bars=2` pokazywał 3 świece: `index-1, index, index+1`), niespójnie z `redraw`'s własną formułą `{from, to: from + bars - 1}` używaną do tego samego problemu przy zachowaniu kadru na zmianie interwału. | **FIXED** w `fbc5322` — ujednolicone do `from = index - floor(bars/2); to = from + bars - 1`; test `"centres an around/bars focus..."` poprawiony, żeby złapać ten błąd (`bars: 2` → oczekiwane `{from:69,to:70}`, nie `{from:69,to:71}`). |
| Medium | `modules/terminal/src/chart/useOlderBars.ts` + `Chart.tsx`, `olderReader` | Bieg pagera, który wyczerpał `MAX_PAGES=20` stron, z których każda coś wniosła, kończy się statusem `"idle"` jak każdy inny — a efekt rozliczający kadr nasłuchuje tylko `"exhausted"`/`"error"`. Kadr zostawał w `pendingFocusRef`: wykres się nie ruszał, `onFocusRequestSettled` nie padało, a `gridStore` oferował to samo żądanie aż do zmiany symbolu. Pierwotnie zapisane niżej jako Gap. | **FIXED** w `5921e8d` — `OlderBarsReader.stoppedShort?()`, wołane, gdy bieg kończy się z `needsMore()` wciąż prawdziwym. Świadomie **nie** `"exhausted"`, które twierdziłoby, że archiwum nie ma nic starszego, a tu ma. `Chart` rozlicza kadr wobec tego, co faktycznie dociągnął — przypadek, dla którego istnieje `overlapsSeries`. Test `"settles a focus the pager ran out of pages before reaching"` sprawdzony jako czerwony bez poprawki. |
| High | `modules/terminal/src/chart/Chart.tsx`, `pursueFocus` + `useOlderBars` | Kadr nazywający odległy moment był **dochodzony pieszo**: strona pagera to rozpiętość, jaką zajmuje 300 najstarszych narysowanych świec — na MINUTE_5 zmierzone 1,04 dnia kalendarza — a `MAX_PAGES=20` domyka bieg na ~21 dniach, w dwudziestu kolejnych żądaniach HTTP. Do połowy marca z żywej krawędzi trzeba ~145 stron. Po wyczerpaniu budżetu `applyFocusToView` liczyło `nearestBarIndex` dla momentu starszego niż cokolwiek narysowane → indeks 0 → wykres pokazywał najstarsze dociągnięte świece, wyglądając na udany ruch. Zgłoszone przez operatora jako „proszę o połowę marca, przenosi na połowę kwietnia, i dane długo się dociągają" — jeden mechanizm, oba objawy. Model był bez winy: `tool_calls` niesie `around: 2026-03-15T12:00:00Z`. | **FIXED** w `43756d9` — `OlderBarsReader.reachBack(target)`: jeden odczyt okna `[cel, najstarsza narysowana]` zamiast wędrówki. `lastBars` zostaje przy pagerze, bo nie nazywa momentu. Kadr `around`+`bars` sięga o połowę swoich świec przed nazwany moment, inaczej wychodzi przesunięty o pół ekranu. Test `"asks for the whole window to a distant focus in one read"` sprawdzony jako czerwony bez poprawki (9 odczytów zamiast 1). |

Poza tym: żadnych innych ustaleń. Przejrzano cały diff `06acb0f..81db4e6` (backend:
`models.py`, `store.py`, `contract.py`, `tools/chart.py`, migracja `0006`; terminal:
`Chart.tsx`, `useOlderBars`'s `needsMore` (bez zmian w samym pliku), `gridStore.ts`,
`GridView.tsx`, `chartControl.ts`, `agentApi.ts`, `testDoubles.ts`, `data/types.ts`) —
zwłaszcza mechanizm rozliczania kadru w `applyOlder`/efekcie `exhausted`/`error` (opisany
w design.md jako świadome odejście od obserwowania przejścia `loading`→nie-`loading`, bo
React potrafi to zbić w jeden render) oraz rozróżnienie ciała i cleanupu efektu przy
zmianie rozdzielczości (`previousParamsRef` musi być aktualizowany w ciele, nie w
cleanupie, bo cleanup domyka się na starych wartościach) — bez dalszych usterek.

## Spec coverage

### `agent-chart-control` (delta)

| Requirement / Scenario | Proven by |
|---|---|
| Narzędzie ustawia zawartość aktywnego slotu — Model pokazuje średnią | `test_chart_tool.py::test_a_full_set_is_recorded_as_one_command` |
| — Model zmienia sam interwał | `test_chart_tool.py::test_one_field_alone_says_nothing_about_the_others` |
| — Model podaje pełny zestaw wskaźników | `test_chart_tool.py::test_a_full_set_is_recorded_as_one_command` |
| — Model przenosi operatora na wskazaną datę | `test_chart_focus_tool.py::test_a_range_moves_the_operator_to_a_date` |
| — Model przybliża ostatnie świece | `test_chart_focus_tool.py::test_last_bars_zooms_to_the_end_of_the_series` |
| — Polecenie bez kadru zostawia widok | `chartControl.test.ts::"leaves the focus request alone when the command carries none"` |
| Odmowa narzędzia nazywa, co poprawić — Symbol, którego archiwum nie zbiera | `test_chart_tool.py::test_a_symbol_the_archive_does_not_collect_is_refused_with_the_ones_it_does` |
| — Parametr poza granicami katalogu | `test_chart_tool.py::test_a_parameter_out_of_range_names_the_range` |
| — Odmowa nie zostawia śladu na wykresie | `test_chart_tool.py::test_an_unknown_indicator_is_refused_and_nothing_is_written` |
| — Kadr podany dwoma sposobami naraz | `test_chart_focus_tool.py::test_two_shapes_at_once_is_refused` |
| — Odwrócony zakres kadru | `test_chart_focus_tool.py::test_an_inverted_range_names_both_ends` |
| — Liczba świec poza granicami | `test_chart_focus_tool.py::test_a_bar_count_below_the_floor_names_the_bounds` / `test_a_bar_count_above_the_ceiling_names_the_bounds` (parametryzowane `bars`/`last_bars`) |
| — Kadr w całości w przyszłości | `test_chart_focus_tool.py::test_a_range_entirely_in_the_future_is_refused` / `test_a_point_in_the_future_is_refused` |

### `agent-chat` (delta)

| Requirement / Scenario | Proven by |
|---|---|
| Tura wie, co terminal właśnie rysuje — Pytanie o to, co widać | `test_sessions_router.py::test_a_turn_carrying_a_chart_snapshot_hands_it_to_the_model` (bez pola widocznego zakresu — istniejący test) + `test_chart_snapshot.py::test_as_context_names_the_visible_span` (nowa część) |
| — Pytanie o przesunięcie względem tego, co widać | **brak** — patrz Gaps |
| — Żądanie bez migawki | `test_sessions_router.py::test_a_turn_without_a_snapshot_runs_the_prompt_untouched` |
| — Migawka bez widocznego fragmentu | `test_chart_snapshot.py::test_as_context_omits_the_span_when_absent` / `test_as_context_omits_the_span_when_only_one_half_is_known`; `agentApi.test.ts::"sends neither half of the visible span when only one is known"` |
| — Migawka nie trafia do transkryptu | `test_sessions_router.py::test_a_turn_carrying_a_chart_snapshot_hands_it_to_the_model` |

### `terminal-chart` (delta)

| Requirement / Scenario | Proven by |
|---|---|
| Wykres przyjmuje kadr z zewnątrz — Kadr na fragment już narysowany | `Chart.test.tsx::"applies a from/to focus already covered by the drawn series, reading nothing more"` |
| — Kadr sięgający przed narysowaną historię | `Chart.test.tsx::"pages older history to reach a from/to focus, then applies it"` |
| — Kadr na okres, którego archiwum nie ma | `Chart.test.tsx::"skips a focus the archive has nothing for, leaves the view alone, and says so"` |
| — Operator przewija po zastosowanym kadrze | `Chart.test.tsx::"lets the operator pan freely after a focus applies, without snapping back"` |
| Rozdzielczość zmienia się bez przeładowania — Wybór innego interwału | istniejący test sprzed tej zmiany (niezmodyfikowany aspekt) |
| — Szybka zmiana kilku rozdzielczości pod rząd | istniejący test sprzed tej zmiany (niezmodyfikowany aspekt) |
| — Zmiana interwału nad fragmentem historii | `Chart.test.tsx::"keeps the same stretch of time, converted to the new interval's own candle count"` |
| — Zmiana interwału przy prawej krawędzi | `Chart.test.tsx::"keeps standing at the live edge, on the new interval's own newest candle"` |
| — Odcinek zbyt krótki dla nowego interwału | `Chart.test.tsx::"floors an interval mismatch too small to read at, instead of showing one or two candles"` |

Dodatkowo, bez własnego wiersza w specach, ale sprawdzone: brak zmiany kadru przy pierwszym
rysowaniu slotu i przy zmianie symbolu (`Chart.test.tsx::"still fits the whole series on a
slot's very first draw"`, `"does not touch the frame when the symbol changes instead of the
resolution"`) oraz zaokrąglanie osobno dla dwóch wywołań `applyFocusToView`
i `redraw`'s formuły centrowania (ten sam wzór, sprawdzony przez błąd znaleziony w tym
review — patrz Findings).

## Gaps

- **„Pytanie o przesunięcie względem tego, co widać"** (`agent-chat`) — sprawdza, że model
  *rozumuje* z migawki widocznego zakresu i liczy sensowny nowy kadr. To zachowanie modelu
  językowego, nie deterministycznego kodu — żaden test jednostkowy ani integracyjny go nie
  dowodzi. Migawka dociera do promptu poprawnie (`test_as_context_names_the_visible_span`),
  ale to, co model z niej zrobi, jest poza zasięgiem tego review.
- ~~**Kadr `from`/`to` poza budżetem pagera**~~ — **zamknięte** w `5921e8d`; przeniesione do
  Findings. Bieg, który wyczerpał budżet stron z niezaspokojonym `needsMore()`, mówi to
  teraz wprost (`stoppedShort`), a `Chart` rozlicza kadr wobec dociągniętego fragmentu.
- **Task 9.3, ręczne przejście na żywym stacku** — w toku poza tym dokumentem. Pierwszy
  wynik operatora (przed potwierdzonym restartem stacku) opisany w Verdict. Drugi przebieg
  znalazł to, czego żaden test nie znalazł: kadr na odległy miesiąc lądował w złym miejscu
  (Findings, wiersz trzeci) — czyli dokładnie to, po co ten task istnieje, i powód, żeby
  nie zamykać go z pamięci. Po poprawce `43756d9` wymaga powtórzenia: „pokaż połowę marca
  na M5", potem powrót na żywą krawędź i zmiana interwału nad tym samym miejscem.
